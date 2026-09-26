# Omniscient

Omniscient is a smart campus assistant for students at Dedan Kimathi University of Technology (DeKUT), Nyeri, Kenya. It's an agentic workspace — not a generic chatbot — that helps students with housing, academics/timetables, past examination papers, and campus complaints, with a live streamed execution trace so the student can see what Omniscient is actually doing on their behalf.

The product runs completely on seeded demo data with no external credentials required. Rumia (a separate, existing production system) is treated as an external, optional data source behind a clean repository boundary — see [Rumia integration](#rumia-integration-boundary) below.

## Architecture at a glance

```
omniscient/
  backend/            FastAPI + SQLAlchemy (async) + PostgreSQL + pgvector + Alembic
    app/
      api/routes/      HTTP + streaming endpoints
      agents/          Router, orchestrator, LLM provider abstraction + failover
      tools/           Typed, independently-testable tool registry
      repositories/    Domain data access (Mock + Rumia boundary) + vector search
      models/          SQLAlchemy ORM models
      schemas/         Pydantic request/response/validation models
      services/        Auth, personalization, file storage, embeddings, RAG indexing
      core/            Config, security, logging, rate limiting
      db/              Session, base, seed data, vector column type
    migrations/         Alembic migrations
    tests/              pytest suite (168 tests)
  frontend/            React + TypeScript + Vite, mobile-first
    src/
      pages/            Route-level screens
      components/       Layout, chat, housing, academics, past papers, complaints, admin
      api/client.ts      Typed API client + SSE streaming consumer
      context/           Auth context
  infra/
    caddy/              TLS terminator + reverse proxy (Caddyfile)
    deploy/             VM bootstrap and rollout scripts
  docs/                Architecture and deployment notes
  docker-compose.yml     Production stack (Caddy, frontend, backend, Postgres+pgvector)
  docker-compose.dev.yml Local development stack (seeded demo data, published ports)
  .github/workflows/     CI on every push, deploy on a v* tag
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design, [`docs/LAUNCH_CHECKLIST.md`](docs/LAUNCH_CHECKLIST.md) for the ordered path from "code written" to a live site, [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for running this on Oracle Cloud — including the cost analysis that determines the instance shape — and [`docs/VERCEL_DEPLOYMENT.md`](docs/VERCEL_DEPLOYMENT.md) for Vercel (frontend) + Neon (database) + Railway/Render/Fly.io (backend).

## Quickstart (local development, no Docker)

### Prerequisites
- Python 3.11+
- Node.js **22+** (pinned in `frontend/.nvmrc` and `engines`; Vite 8 will not run on Node 18)
- PostgreSQL 14+ with the **pgvector** extension available

Using `docker compose -f docker-compose.dev.yml up -d --build` avoids
installing PostgreSQL and pgvector yourself.

### 1. Database
```bash
sudo -u postgres psql -c "CREATE ROLE omniscient LOGIN PASSWORD 'omniscient';"
sudo -u postgres psql -c "CREATE DATABASE omniscient OWNER omniscient;"
```

### 2. Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp ../.env.example ../.env   # then edit DATABASE_URL etc. if needed

alembic upgrade head
python -m app.scripts_entry seed --if-empty

uvicorn app.main:app --reload --port 8000
```
Backend runs at `http://localhost:8000`. Health check: `GET /api/health`.

Demo login: `jane.wanjiru@dekut.ac.ke` / `Passw0rd!`
Demo admin login: `admin@dekut.ac.ke` / `AdminPass1!` (seeded with `is_admin=True` — see [Admin dashboard](#admin-dashboard) below).

## Generative UI

Chat responses aren't plain text: the orchestrator deterministically maps each tool's own typed result to one of a fixed set of content blocks — table, list, card, comparison, file, image, chart — streamed as `content_block` SSE events alongside the existing trace, persisted per-message, and rendered by dedicated React components that reuse the app's own design tokens. The model never constructs UI itself (it only sees the same tool results and writes the prose around them); which block appears is entirely a function of which tool ran and its data shape, e.g. `search_hostels` → table (+ a price chart once there are 2+ results), `search_past_papers` → downloadable file list, `file_complaint` → a status card. Students can also attach an image or document to a message (paperclip button); images are sent as real multimodal content to vision-capable providers (Anthropic/OpenAI-compatible), while the mock provider gives an honest "I can't actually see images in offline mode" reply rather than fabricating a description.

### 3. Frontend
```bash
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000" > .env
npm run dev
```
Frontend runs at `http://localhost:5173`.

### 4. Run tests
```bash
# Backend: repositories, tools, agent orchestration, API, streaming, auth,
# admin, RAG chunking and provider failover.
cd backend && source .venv/bin/activate
OMNISCIENT_ENV_FILE= pytest -q
ruff check .

# Frontend: component + API-client tests
cd frontend && npm test
```

`OMNISCIENT_ENV_FILE=` matters — see [the `.env` trap](#the-env-trap-in-tests).
Lint is `ruff check` only; `ruff format` is deliberately not part of the
workflow, because this codebase was never formatted with it and adopting
it now would bury any real change under a repo-wide reformat diff.

## Admin dashboard

`/admin` (linked from the sidebar for admin accounts only) lets an admin feed and correct every domain Omniscient answers from — hostels, programmes/courses/timetable/deadlines, past papers, and complaint status — through the exact same repositories the chat agent reads at answer time, so there is no separate "admin data path" that could drift from what the agent grounds its answers in. It also surfaces `/api/admin/insights`: real, already-captured usage signal (classified question topics, complaint category/status breakdowns) — the honest interpretation of "learning from users" here, not a claim that any model is being retrained.

Authorization is enforced server-side against an `is_admin` flag on the `students` table, checked fresh from the database on every request — never anything a client or the LLM claims about itself. To promote an existing (already-registered) student to admin:
```bash
cd backend && source .venv/bin/activate
python -m app.scripts_entry promote-admin some.student@dekut.ac.ke
```
The seeded demo dataset also ships one ready-made admin account (see the login above).

## Docker Compose

`docker-compose.yml` is the **production** stack: Caddy terminating TLS for
`omniscient.co.ke`, the frontend, the backend, and PostgreSQL with
pgvector. It does not seed demo data, does not publish the database, and
caps each container's memory.

`docker-compose.dev.yml` is **local development**: images build from
source, demo data is seeded on first boot, and the database and API are
published to localhost.

```bash
cp .env.example .env   # edit values as needed
docker compose -f docker-compose.dev.yml up -d --build
```

For Oracle Cloud, including the bootstrap script, the CI/CD pipeline, the
GitHub secrets required, and the reasoning behind the instance shape, see
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## AI provider configuration

Omniscient never requires a live LLM credential to work. `LLM_PROVIDER=mock` (the default) uses a deterministic, offline provider that performs real intent classification, parameter extraction, and tool selection using rules tuned for DeKUT student messages — the whole agent pipeline (router → tools → streamed trace → grounded answer) works end-to-end without any API key.

Set `LLM_PROVIDER` to `deepseek`, `groq`, `grok` (xAI), `openai`, `anthropic`, or `custom` (any other OpenAI-compatible endpoint) plus `LLM_MODEL`/`LLM_API_KEY` to use a real model instead. Every provider implements the exact same interface (`app/agents/providers/base.py`), so switching — or adding another provider later — never touches application code, only `.env`. See `docs/ARCHITECTURE.md` for how `deepseek`/`groq`/`grok`/`openai`/`custom` all share one `OpenAICompatibleProvider` implementation.

### Failing over between providers

A campus assistant that stops answering because one vendor returned a 429
is not a campus assistant. `LLM_FALLBACK_PROVIDER` names a second
provider to try when the first cannot serve a turn:

```bash
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-flash
LLM_API_KEY=...
LLM_FALLBACK_PROVIDER=groq
LLM_FALLBACK_MODEL=openai/gpt-oss-20b
LLM_FALLBACK_API_KEY=...
```

Three details make this safe rather than merely convenient:

- **The trace tells the truth.** `display_name` is read from whichever
  provider is currently answering, so the execution stream names the
  model that actually produced the answer, not the one configured first.
- **A half-sent answer is never spliced.** Once tokens have reached the
  student, a mid-stream failure surfaces instead of retrying, because two
  answers joined together read as one incoherent reply.
- **A dead provider stays dead.** After its first failure it is skipped
  for the rest of the process, so an outage costs one slow turn rather
  than one slow turn per student per message.

Only `ProviderUnavailable` triggers a failover; any other exception is a
bug and retrying it elsewhere would hide that instead of surfacing it.

## Past-paper search (RAG)

`search_past_papers` matches papers by metadata — course code, programme,
year. `search_past_paper_content` searches *inside* the papers, so
"how did question 3b go" or "show me an example of a B-tree insertion"
works when no course code is known.

The pipeline: PDF → text extraction (`pypdf`) → page-aligned overlapping
chunks → ONNX embeddings → `pgvector` with an HNSW index → similarity
search → cited excerpts the model is grounded on and cannot go beyond.

```bash
EMBEDDING_ENABLED=true
RAG_ENABLED=true
EMBEDDING_BACKEND=local          # in-process ONNX, no extra container
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSIONS=384
```

Some decisions worth knowing:

- **Embeddings are self-hosted, in-process.** DeepSeek and Groq do not
  serve an embeddings API, so there is no choice of hosted provider to
  make — and no third party who can fail. ONNX rather than PyTorch keeps
  the image and the RAM cost to roughly what a 90 MB model should be.
  Inference is dispatched to a worker thread, because it is CPU-bound
  and would otherwise stall the event loop mid-stream for every student.
  `EMBEDDING_BACKEND=tei` switches to a sidecar with no code change.
- **Chunks are page-aligned and overlapping.** A window that stops
  mid-page makes its recorded page range a lie, and a wrong citation is
  worse than none. The overlap is why a question straddling a boundary is
  still retrievable from one chunk.
- **Failures degrade, they do not break.** A missing model, an unbuilt
  index, or a database without pgvector all report "search unavailable"
  and the assistant still answers from its other tools. Scanned PDFs with
  no text layer are rejected with a clear message instead of being
  indexed as permanently unsearchable.
- **Starting it is refused when it cannot work.** `RAG_ENABLED` without
  `EMBEDDING_ENABLED`, or with the mock provider, fails at startup —
  because a feature that can only ever return nothing is worse than an
  absent one.

Rebuild the index from the admin dashboard (Past papers) or:

```bash
docker compose exec backend python -m app.scripts_entry reindex-past-papers [--force]
```


## Rumia integration boundary

Rumia is a separate, existing production system. Omniscient reads its housing data and does nothing else to it:

- **No shared database.** Omniscient has its own PostgreSQL database and schema, and never reads or writes Rumia's.
- **No credentials.** Housing is read over Rumia's own public, unauthenticated HTTP API (`RUMIA_API_BASE_URL`, default `https://rumia.co.ke/api/v1`). There is no key, token or connection string to hold, rotate, or leak — a transport that cannot authenticate cannot escalate its own access.
- **No write path.** The repository exposes no write method, so "Omniscient mutated Rumia" is not a mistake anyone can make here: there is no code to make it with. Admin hostel CRUD returns `409` while Rumia is the source.
- **No schema coupling.** Rumia's `listings` table is read through its own public contract, so a migration on Rumia's side cannot break us at the SQL level.
- **Switchable by config only.** `RUMIA_DB_MODE=disabled` (the default) uses `MockHostelRepository` against local seeded demo data with no outbound calls at all; `enabled` uses `RumiaApiHostelRepository`. No application code changes either way.
- **Rumia is campus-scoped**, so `RUMIA_CAMPUS_SLUG` (default `dekut`) selects the campus rather than assuming one.

A direct Postgres transport to Rumia was considered and deliberately not built: it would require either provisioning a role *inside* someone else's production database or reusing a superuser credential, and neither is a fair price for data Rumia already serves read-only over HTTP. `RUMIA_DATABASE_URL` therefore has no consumer, and a test asserts the factory cannot grow such a branch.

Rumia's vocabulary is mapped explicitly in `repositories/hostel_repository.py` — a Rumia "listing" becomes an Omniscient "hostel", free-text distances ("10 mins walk", "Over 3 kilometres", "5 mins drive/45 mins walk") become km, and Rumia's amenity labels are normalised onto the vocabulary Omniscient's own seeded data uses, so one filter means the same thing whichever repository is active.

### Caching, because Rumia is slow

Rumia's listings endpoint takes 4-6 seconds to answer, so the cost that matters is the number of upstream calls. Three things keep that at roughly one per TTL instead of one per request:

- **One instance, reused.** `get_hostel_repository` is a FastAPI dependency and so runs per request; the repository (and its `httpx` client, connection pool and cache) is memoised on the config values. Building one per request would mean a fresh TLS handshake each time and a permanently empty cache.
- **One campus feed, not one cache entry per query.** The whole (small) DeKUT feed is fetched once and every query filters it in memory. Caching per filter combination would still cost one upstream call per distinct query — no better than no cache for someone clicking through filters. Mapping also happens once per fetch, not once per query.
- **Stale-while-revalidate.** Once a feed exists it is served immediately and refreshed in the background, so nobody waits on Rumia mid-conversation. Past `RUMIA_CACHE_TTL_SECONDS + 600` the refresh is awaited instead, and a failed refresh keeps serving the existing feed rather than reporting "no hostels found". The feed is also warmed at application startup, so the first student to ask about housing doesn't pay the cold fetch either. A failed warm-up is logged and ignored.

Measured effect: `GET /api/housing/hostels` went from 4.4-8.6s per request to ~5ms warm, and a full chat turn from ~5s to ~0.2s.

Two behaviours worth knowing:

- **`verified`** is not a field Rumia's API publishes — Rumia vets listings before they go live, so `RUMIA_TREAT_ACTIVE_AS_VERIFIED=true` treats a live listing as verified. That is an assertion about Rumia's process, which is why it is a switch: set it false and a `verified_only` search returns nothing rather than passing off unvetted listings.
- **An unreachable Rumia is never reported as "no hostels found."** The tool returns a failed step with the real reason, and `/api/housing/*` returns `503` — because to a student, an empty list reads as "there is nowhere to live near campus."

## Environment variables

See [`.env.example`](.env.example) for the full, documented list (application, database, AI provider and fallback, embeddings and retrieval, Rumia boundary, storage, rate limiting). Never commit a real `.env` file — only `.env.example` with placeholder values is tracked in git.

On the production VM, `.env` is created once by an operator and is never read, written, or logged by CI. The deploy job receives an SSH key and nothing else.

### The `.env` trap in tests

`backend/.env` is a **symlink to the repo-root `.env`**, and the app reads a dotenv file relative to the process working directory. So a developer's local settings can silently become the test environment — which is exactly how the housing tests came to call the **live Rumia API** and assert against its listings instead of their own fixtures.

Two consequences, both now handled:

- `OMNISCIENT_ENV_FILE=` (empty) switches dotenv loading off. It has to be decided in `app/core/config.py` at import time; mutating `Settings.model_config["env_file"]` afterwards does **not** work on pydantic-settings 2.7.x, because the dotenv source is built from the config captured when the class was created.
- The test suite pins every variable it depends on through `os.environ`, which pydantic-settings gives precedence over any env file. The result is the same world on a laptop, in CI, and in a container.

## Continuous integration and delivery

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | every push, every PR | `ruff check` + pytest; `oxlint` + `tsc` + vitest + a real frontend build; Alembic applied to a real PostgreSQL with pgvector, with the extension and HNSW index asserted afterwards and the chain downgraded and re-upgraded; and the backend image built for `linux/arm64` |
| `deploy.yml` | a `v*` tag, or manual | Builds both images for `linux/amd64,linux/arm64`, pushes to GHCR with provenance and an SBOM, rolls out over SSH, then smoke-tests the public URL |

Two jobs earn their keep:

- **The migrations job** exists because a migration can be valid Python and
  still be invalid SQL. `CREATE EXTENSION vector` and
  `CREATE INDEX ... USING hnsw` are only verifiable against a real server.
- **The arm64 build** is what makes running on an Oracle Ampere A1 safe.
  The biggest risk of an ARM instance is a wheel or base image that does
  not exist for `aarch64`, so the backend Dockerfile downloads the
  embedding model at build time specifically to make that failure appear
  in CI rather than as a reindex that silently produces nothing in
  production.

Deploys are serialised by a concurrency group: two overlapping deploys
would otherwise restart the same containers against each other
mid-migration. A failed rollout reads the image the *running* container
reports and reverts to it.

## Design decisions worth knowing

- **Brand color**: the repository ships with no design files, so the product's visual system was built from the brand/token spec given directly in the build brief — Rumia's restrained green (`#16A34A`), not indigo/violet, per the brief's explicit instruction. Layout, spacing, and interaction patterns follow a calm, border-led, Claude-desktop-like workspace: sidebar + main content + a live activity panel on desktop, collapsing to bottom navigation and a swipe-up activity drawer on mobile.
- **Streaming**: `POST /api/chat` uses Server-Sent Events (plain `text/event-stream` over a chunked HTTP response) rather than WebSockets — the trace is one-directional (server → client) per turn, so SSE is the simplest reliable mechanism that still lets the frontend render tool calls and results live as they happen.
- **Tool safety**: the LLM never talks to the database directly and is never trusted to authorize an action. Every tool validates its own inputs (Pydantic) and enforces its own authorization (e.g. `file_complaint` requires an authenticated student regardless of what the model claims).
