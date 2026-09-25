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
    tests/              pytest suite (46+ tests)
  frontend/            React + TypeScript + Vite, mobile-first
    src/
      pages/            Route-level screens
      components/       Layout, chat, housing, academics, past papers, complaints
      api/client.ts      Typed API client + SSE streaming consumer
      context/           Auth context
  docs/                Architecture and deployment notes
  docker-compose.yml   Postgres + backend + frontend, for local or single-VM deployment
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design, and [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for running this on Oracle Cloud.

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
# Backend (46 tests: repositories, tools, agent orchestration, API, streaming, auth)
cd backend && source .venv/bin/activate && pytest

# Frontend (component + API-client tests)
cd frontend && npm test
```

## Docker Compose

```bash
cp .env.example .env   # edit values as needed
docker compose up --build
```
This starts PostgreSQL, runs migrations + seed data, then the backend (`:8000`) and the frontend (`:5173`, served via nginx). See `docs/DEPLOYMENT.md` for Oracle Cloud notes and known constraints when building images in network-restricted environments.

## AI provider configuration

Omniscient never requires a live LLM credential to work. `LLM_PROVIDER=mock` (the default) uses a deterministic, offline provider that performs real intent classification, parameter extraction, and tool selection using rules tuned for DeKUT student messages — the whole agent pipeline (router → tools → streamed trace → grounded answer) works end-to-end without any API key.

Set `LLM_PROVIDER=anthropic`, `LLM_MODEL`, and `LLM_API_KEY` to use a real Claude model via native tool-use instead. Both providers implement the exact same interface (`app/agents/providers/base.py`), so nothing else in the app changes.

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
