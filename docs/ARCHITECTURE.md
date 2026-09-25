# Architecture

## Overview

Omniscient is a modular monolith: one FastAPI backend, one PostgreSQL database, one React frontend. This is deliberate — the product is used by a small engineering team and a single campus's worth of traffic, so microservices, an event bus, or Kubernetes would add operational cost without a corresponding benefit. The internal structure (domains, repositories, tools, agents) gives the same separation of concerns a microservice split would, without the deployment overhead.

## Request flow (chat)

```
Student message (POST /api/chat)
        |
        v
Router (agents/router.py)          -- LLM classifies intent, router validates the result
        |
        v
Parameter resolution                -- personalization_service merges remembered
                                        preferences with the current request
                                        (current request always wins)
        |
        v
Tool selection                      -- provider.propose_tool_calls() picks a
                                        registered tool + arguments
        |
        v
Tool execution (tools/registry.py)  -- Pydantic-validated input, its own
                                        authorization check, calls a
                                        repository (never raw SQL/LLM access)
        |
        v
Trace events streamed over SSE      -- status / tool_call / tool_result /
                                        answer_chunk / error / done
        |
        v
Final answer generation             -- provider.stream_final_answer(),
                                        grounded ONLY in tool results
```

Every step above emits a safe, user-facing trace event (`schemas/chat.py:TraceEventOut`) over the `/api/chat` SSE stream. The frontend's `ActivityPanel`/`ExecutionTrace` components render these live — never a placeholder generated after the fact.

**The LLM never touches the database.** It sees only tool results that have already gone through a repository and a typed schema. Trace events never carry chain-of-thought, prompts, secrets, or SQL — see `agents/orchestrator.py` and `_DOMAIN_STATUS`/`_TOOL_RUNNING_MESSAGE` for the exact, reviewed set of user-facing strings.

## Agent layers

1. **Router** (`agents/router.py`) — classifies a message into `housing | academics | past_papers | complaints | general` with a confidence score and structured parameters. Raw model output is validated into `IntentResult` before anything downstream sees it; an invalid/out-of-domain result falls back to `general` rather than propagating.
2. **Tool registry** (`tools/registry.py` + `tools/*_tools.py`) — every capability (`search_hostels`, `get_hostel`, `get_timetable`, `list_academic_deadlines`, `search_past_papers`, `get_past_paper`, `file_complaint`, `get_complaint_status`) is a `Tool`: a name, an LLM-facing description, a Pydantic input model, and an async handler. Handlers are pure business logic against repository *interfaces* — independently unit-testable with no LLM in the loop (see `tests/test_tools.py`).
3. **Orchestrator** (`agents/orchestrator.py`) — runs the full loop above and yields `TraceEventOut` events as an async generator.

### AI provider abstraction

`agents/providers/base.py` defines `LLMProvider` with three methods: `classify_intent`, `propose_tool_calls`, `stream_final_answer`. Two implementations exist:

- **`MockProvider`** (default, `LLM_PROVIDER=mock`) — deterministic, offline, keyword/regex-based. It performs real intent classification and parameter extraction tuned for DeKUT student messages (budgets, Nyeri-area names, day-of-week, complaint categories), so the full product is usable and testable without any API key.
- **`AnthropicProvider`** (`LLM_PROVIDER=anthropic`) — uses the Anthropic Messages API with native tool-use for structured classification/tool-selection and streaming for the final answer.
- **`OpenAICompatibleProvider`** (`LLM_PROVIDER=openai|grok|deepseek|custom`) — one implementation for every provider that speaks the OpenAI Chat Completions wire format. `factory.py` resolves the right `base_url` for each named provider (`grok` → `api.x.ai`, `deepseek` → `api.deepseek.com`, `openai` → `api.openai.com`); `custom` takes any `LLM_API_BASE` (Groq, Together, Mistral, a self-hosted vLLM/Ollama endpoint, ...). Grok is the intended primary real provider; swapping to DeepSeek, or adding a sixth OpenAI-compatible provider later, is a `.env` change only — see `PROVIDER_BASE_URLS` in `agents/providers/factory.py`.

Any provider failure raises `ProviderUnavailable`, which the orchestrator turns into a graceful `error` trace event and a friendly message — never a fabricated result. Each provider also carries a `display_name` (e.g. "Grok (xAI)") that the orchestrator surfaces in the first trace event, so the activity panel can show which model is doing the thinking.

## Repository layer & the Rumia boundary

Every domain has a repository interface (`repositories/*.py`) that tools depend on, never a concrete database or ORM session directly. Housing is the one domain with two implementations, because it's the one domain Rumia is expected to eventually provide:

```python
class HostelRepository(ABC): ...
class MockHostelRepository(HostelRepository): ...       # Omniscient's own seeded data (active today)
class RumiaPostgresHostelRepository(HostelRepository): ...  # read-only Rumia listings (future)

def get_hostel_repository(session, settings) -> HostelRepository:
    if settings.rumia_db_mode == "enabled" and settings.rumia_database_url:
        return RumiaPostgresHostelRepository(settings.rumia_database_url)
    return MockHostelRepository(session)
```

Switching data sources is a configuration change (`RUMIA_DB_MODE`, `RUMIA_DATABASE_URL`), not a code change. `RumiaPostgresHostelRepository` only ever reads; it is never given write access and never touches Rumia's user or lead tables.

Academics, past papers, and complaints are Omniscient-owned data (there is no Rumia equivalent for them), so they have a single SQL-backed implementation each.

## Admin dashboard

`api/routes/admin.py` (`/api/admin/*`) exposes CRUD for every domain — hostels, programmes/courses/timetable/deadlines, past papers, complaint status — plus `GET /api/admin/insights`. Every route depends on `get_current_admin` (`api/deps.py`), which loads the authenticated student from the database and checks its `is_admin` column; nothing a client or the model claims about itself is ever trusted for this check.

The routes call the same repository write methods the read-side tools already depend on (`HostelRepository.create/update/delete`, `AcademicRepository.create_course`, etc.), so admin-authored content is immediately what the chat agent grounds its answers in — there is no separate "admin data path" to keep in sync. `HostelRepository` write methods raise `HostelWriteNotSupported` on `RumiaPostgresHostelRepository`, since Rumia-backed housing data stays strictly read-only even from the admin surface.

`InsightsOut` (`services/insights_service.py`) aggregates real, already-captured signal — `ChatMessage.intent` counts and complaint category/status counts — rather than fabricating a retraining claim; this is the honest interpretation of the brief's "learn from users" requirement.

## Personalization

`services/personalization_service.py` stores a small, fixed set of fields on `Student.preferences` (housing budget/area today) — never an open-ended memory dump. `resolve_housing_preferences()` is the one function that decides what to use: an explicit value in the *current* message always wins over a remembered one, and the trace tells the student when a remembered preference was applied (e.g. "Using your usual budget of KSh 8,000 since none was given this time").

## Security posture

- Passwords are hashed with bcrypt (via passlib); JWTs are signed with `SECRET_KEY` and carry only the student id.
- Every tool re-checks its own authorization (`ToolContext.require_student()` / `requires_auth=True`) — the model claiming a user is authenticated or an admin is never sufficient on its own.
- All tool/API inputs are validated with Pydantic before touching business logic.
- File uploads are validated for content type, size (10 MB), and filename before being written (`services/storage/base.py:validate_upload`); nothing uploaded is ever executed.
- A lightweight in-process rate limiter (`core/rate_limit.py`) applies a default per-IP limit app-wide and a stricter limit to `/api/chat`.
- Structured logs (`core/logging.py`) redact password/token/secret/api_key/authorization keys and never log full conversation text.
- Every unhandled exception is caught at the top level and returned as a generic message with a correlation id — internals are never leaked to the client.

## Frontend

React + TypeScript + Vite, mobile-first. `AppShell` provides the three-zone desktop workspace (sidebar, main content, activity panel) that collapses to a top bar + bottom navigation + swipe-up activity drawer on mobile. The chat UI intentionally avoids heavy chat-bubble styling in favor of a calmer, document-like layout (assistant text is plain, user turns get a soft subtle background) closer to a professional agent workspace than a generic chatbot.

`hooks/useChatStream.ts` + `api/client.ts:streamChat()` consume the SSE stream directly via `fetch` + a `ReadableStream` reader (not `EventSource`, since the request is a `POST` with a JSON body and an `Authorization` header) and update messages/trace state as events arrive.

**The activity panel only opens in response to an instruction.** It is not a persistent empty-state column: `HomePage`'s `ChatWorkspace` only mounts `ActivityPanel` once `trace.length > 0 || isStreaming` is true, so a student sees the full-width chat until they actually send a message — the panel (desktop column, or the mobile "Activity" toggle + swipe-up drawer) appears the moment there's real activity to show, and shows which provider is doing the thinking (`display_name` from the backend, e.g. "Grok (xAI)", surfaced via the first `status` trace event).

**Conversation history** (`Sidebar`'s "Recent" section, authenticated students only) is powered by `GET /api/chat/sessions`, refetched on route change (`hooks/useRecentSessions.ts`). Sessions are auto-titled from their first message (`ChatRepository.set_title`, called once when a session is created). Switching conversations — including starting a new one — is implemented by keying `ChatWorkspace` on the `?session=` query param: navigating changes the key, which remounts a fresh `useChatStream` instance rather than trying to patch a shared state object in place.
