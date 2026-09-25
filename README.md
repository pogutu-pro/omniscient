# Omniscient

Omniscient is a smart campus assistant for students at Dedan Kimathi University of Technology (DeKUT), Nyeri, Kenya. It's an agentic workspace — not a generic chatbot — that helps students with housing, academics/timetables, past examination papers, and campus complaints, with a live streamed execution trace so the student can see what Omniscient is actually doing on their behalf.

The product runs completely on seeded demo data with no external credentials required. Rumia (a separate, existing production system) is treated as an external, optional data source behind a clean repository boundary — see [Rumia integration](#rumia-integration-boundary) below.

## Architecture at a glance

```
omniscient/
  backend/            FastAPI + SQLAlchemy (async) + PostgreSQL + Alembic
    app/
      api/routes/      HTTP + streaming endpoints
      agents/          Router, orchestrator, LLM provider abstraction
      tools/           Typed, independently-testable tool registry
      repositories/    Domain data access (Mock + Rumia boundary)
      models/          SQLAlchemy ORM models
      schemas/         Pydantic request/response/validation models
      services/        Auth, personalization, file storage
      core/            Config, security, logging, rate limiting
      db/              Session, base, seed data
    migrations/         Alembic migrations
    tests/              pytest suite (95+ tests)
  frontend/            React + TypeScript + Vite, mobile-first
    src/
      pages/            Route-level screens
      components/       Layout, chat, housing, academics, past papers, complaints, admin
      api/client.ts      Typed API client + SSE streaming consumer
      context/           Auth context
  docs/                Architecture and deployment notes
  docker-compose.yml   Postgres + backend + frontend, for local or single-VM deployment
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design, [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for running this on Oracle Cloud, and [`docs/VERCEL_DEPLOYMENT.md`](docs/VERCEL_DEPLOYMENT.md) for Vercel (frontend) + Neon (database) + Railway/Render/Fly.io (backend).

## Quickstart (local development, no Docker)

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 14+ running locally

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
# Backend (70+ tests: repositories, tools, agent orchestration, API, streaming, auth, admin)
cd backend && source .venv/bin/activate && pytest

# Frontend (component + API-client tests)
cd frontend && npm test
```

## Admin dashboard

`/admin` (linked from the sidebar for admin accounts only) lets an admin feed and correct every domain Omniscient answers from — hostels, programmes/courses/timetable/deadlines, past papers, and complaint status — through the exact same repositories the chat agent reads at answer time, so there is no separate "admin data path" that could drift from what the agent grounds its answers in. It also surfaces `/api/admin/insights`: real, already-captured usage signal (classified question topics, complaint category/status breakdowns) — the honest interpretation of "learning from users" here, not a claim that any model is being retrained.

Authorization is enforced server-side against an `is_admin` flag on the `students` table, checked fresh from the database on every request — never anything a client or the LLM claims about itself. To promote an existing (already-registered) student to admin:
```bash
cd backend && source .venv/bin/activate
python -m app.scripts_entry promote-admin some.student@dekut.ac.ke
```
The seeded demo dataset also ships one ready-made admin account (see the login above).

## Docker Compose

```bash
cp .env.example .env   # edit values as needed
docker compose up --build
```
This starts PostgreSQL, runs migrations + seed data, then the backend (`:8000`) and the frontend (`:5173`, served via nginx). See `docs/DEPLOYMENT.md` for Oracle Cloud notes and known constraints when building images in network-restricted environments.

## AI provider configuration

Omniscient never requires a live LLM credential to work. `LLM_PROVIDER=mock` (the default) uses a deterministic, offline provider that performs real intent classification, parameter extraction, and tool selection using rules tuned for DeKUT student messages — the whole agent pipeline (router → tools → streamed trace → grounded answer) works end-to-end without any API key.

Set `LLM_PROVIDER` to `grok` (xAI, the intended primary provider), `deepseek`, `openai`, `anthropic`, or `custom` (any other OpenAI-compatible endpoint) plus `LLM_MODEL`/`LLM_API_KEY` to use a real model instead. Every provider implements the exact same interface (`app/agents/providers/base.py`), so switching — or adding a sixth provider later — never touches application code, only `.env`. See `docs/ARCHITECTURE.md` for how `grok`/`deepseek`/`openai`/`custom` all share one `OpenAICompatibleProvider` implementation.

## Rumia integration boundary

Rumia is a separate, existing production system and is never modified, written to, or given elevated access by Omniscient:

- Omniscient has its **own** PostgreSQL database and schema — it never shares Rumia's database.
- Housing data goes through a `HostelRepository` interface with two implementations: `MockHostelRepository` (Omniscient's own seeded demo data, active today) and `RumiaPostgresHostelRepository` (a read-only, listings-only connection, gated by `RUMIA_DB_MODE=enabled` and a real `RUMIA_DATABASE_URL`).
- `RUMIA_DB_MODE=disabled` by default — the app ships fully usable without any Rumia credentials.
- When Rumia access is eventually granted, only `.env` changes; no application code changes are required.
- The Rumia-backed repository is intentionally read-only and never touches user/lead tables.

## Environment variables

See [`.env.example`](.env.example) for the full, documented list (application, database, AI provider, Rumia boundary, storage, rate limiting). Never commit a real `.env` file — only `.env.example` with placeholder values is tracked in git.

## Design decisions worth knowing

- **Brand color**: the repository ships with no design files, so the product's visual system was built from the brand/token spec given directly in the build brief — Rumia's restrained green (`#16A34A`), not indigo/violet, per the brief's explicit instruction. Layout, spacing, and interaction patterns follow a calm, border-led, Claude-desktop-like workspace: sidebar + main content + a live activity panel on desktop, collapsing to bottom navigation and a swipe-up activity drawer on mobile.
- **Streaming**: `POST /api/chat` uses Server-Sent Events (plain `text/event-stream` over a chunked HTTP response) rather than WebSockets — the trace is one-directional (server → client) per turn, so SSE is the simplest reliable mechanism that still lets the frontend render tool calls and results live as they happen.
- **Tool safety**: the LLM never talks to the database directly and is never trusted to authorize an action. Every tool validates its own inputs (Pydantic) and enforces its own authorization (e.g. `file_complaint` requires an authenticated student regardless of what the model claims).
