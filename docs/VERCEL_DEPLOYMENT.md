# Deploying to Vercel

## The honest architecture answer first

**The frontend belongs on Vercel. The backend doesn't — and that's fine.**

Vercel is excellent for the React/Vite frontend: it's a static build, deploys in seconds, and `frontend/vercel.json` (already in this repo) makes it zero-config.

The backend is a stateful FastAPI service: it holds a Postgres connection pool, streams Server-Sent Events for potentially tens of seconds per chat turn, and runs a background heartbeat task per request (see `docs/ARCHITECTURE.md`). That's a long-running-process workload, not a serverless-function workload:

- Vercel serverless functions have hard execution time limits (10s on Hobby, up to 300s on Pro/Enterprise) that a slow LLM response can exceed even with the heartbeat keeping the connection alive.
- True token-by-token SSE streaming support on Vercel's Python runtime is inconsistent across plans and has known rough edges, and isn't something this repo can verify without a live account to test against.
- A serverless function is stateless between invocations, which works against the persistent connection pool `db/session.py` sets up at import time.

So: **frontend on Vercel, backend on a proper long-running host, database on Neon.** This is not extra infrastructure for its own sake — it's three managed services, each doing the one thing it's actually good at, and every piece (Dockerfile, migrations, env vars) already exists in this repo. If you want to attempt the backend on Vercel anyway, the code doesn't stop you (it's a standard ASGI `app` object), but it isn't the path this doc sets you up for, since it can't be verified from here.

## Recommended architecture

```
Vercel (frontend)  --->  Railway / Render / Fly.io (backend, from backend/Dockerfile)  --->  Neon (Postgres)
```

Railway is the closest match to Vercel's git-push-to-deploy experience for a Dockerfile-based service (Render and Fly.io work identically well — same Dockerfile, same env vars, pick whichever you already use). Nothing below is Railway-specific beyond the exact button names.

## 1. Database: Neon

1. Create a Neon project and database.
2. From the Neon dashboard, copy the **pooled** connection string (the one with `-pooler` in the hostname) — this is the one built for many short-lived serverless/edge connections, which is exactly this app's traffic shape.
3. Set (see `.env.example` for the full block):
   ```
   DATABASE_URL=postgresql+asyncpg://<user>:<password>@<project>-pooler.<region>.aws.neon.tech/<db>
   DATABASE_URL_SYNC=postgresql+psycopg2://<user>:<password>@<project>-pooler.<region>.aws.neon.tech/<db>?sslmode=require
   DATABASE_SSL=true
   ```
4. Note: `db/session.py` always disables asyncpg's server-side prepared-statement cache (`statement_cache_size=0`). This is required for correctness against Neon's pooler (or any PgBouncer-style transaction pooler) — without it you'd eventually see intermittent "prepared statement does not exist" errors under load. It's already handled; nothing to configure.
5. Run migrations and seed data once, from your machine (or the backend host's shell), pointed at Neon:
   ```bash
   cd backend
   export DATABASE_URL=postgresql+asyncpg://...  # the Neon pooled URL above
   alembic upgrade head
   python -m app.scripts_entry seed --if-empty
   ```

## 2. Backend: Railway (or Render / Fly.io)

1. Create a new service from this GitHub repo, with **root directory: `backend`**. Railway/Render both auto-detect `backend/Dockerfile` and build from it — no extra config file needed.
2. Set the environment variables listed in [Environment variables](#environment-variables) below, under "Backend".
3. Expose port `8000` (the Dockerfile already `EXPOSE`s it; on Railway this is automatic, on Render set it explicitly).
4. Health check path: `/api/health`.
5. Once deployed, note the public backend URL (e.g. `https://omniscient-api.up.railway.app`) — you'll need it for the frontend's `VITE_API_URL` and the backend's own `API_URL`/`APP_URL`.
6. The container's start command already runs migrations and seeds on boot (`docker-compose.yml`'s command works the same way when the platform runs the image directly) — but since step 1's migration already ran against Neon, this is idempotent (`alembic upgrade head` no-ops if already current, `seed --if-empty` no-ops if data exists).

## 3. Frontend: Vercel

1. Import this repo into Vercel, with **root directory: `frontend`**. `frontend/vercel.json` and Vercel's Vite framework detection handle the rest (build command, output directory, SPA fallback routing).
2. Set the one required environment variable (Project Settings → Environment Variables, for Production, Preview, and Development):
   ```
   VITE_API_URL=https://omniscient-api.up.railway.app
   ```
   Vite bakes `VITE_*` vars into the JS bundle at build time, so changing this requires a redeploy (Vercel does this automatically on every push; a manual "Redeploy" if you only changed the env var).
3. Deploy. Every push gets its own preview URL; the production branch gets your primary domain.

## 4. Close the loop: CORS

The backend only accepts requests from origins you allow. Once you know your Vercel domain(s), set on the backend:

```
CORS_ORIGINS=https://omniscient.vercel.app
CORS_ORIGIN_REGEX=^https://omniscient(-[a-z0-9-]+)?\.vercel\.app$
```

`CORS_ORIGIN_REGEX` is optional but recommended: Vercel mints a new preview URL per branch/PR (`omniscient-git-<branch>-<team>.vercel.app`), and the regex matches all of them automatically instead of you adding each one to `CORS_ORIGINS` by hand. Adjust the pattern to your actual project name once you know it.

## Environment variables

### Frontend (Vercel Project Settings → Environment Variables)

| Variable | Required | Value |
|---|---|---|
| `VITE_API_URL` | Yes | Public URL of the deployed backend, e.g. `https://omniscient-api.up.railway.app` |

### Backend (Railway/Render/Fly.io service settings)

| Variable | Required | Notes |
|---|---|---|
| `APP_ENV` | Yes | `production` |
| `APP_URL` | Yes | Your Vercel URL, e.g. `https://omniscient.vercel.app` |
| `API_URL` | Yes | This backend's own public URL — used to build past-paper download links |
| `SECRET_KEY` | Yes | Long random string (`openssl rand -hex 32`). Never reuse the dev default. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Defaults to `60` |
| `CORS_ORIGINS` | Yes | Your production Vercel domain (comma-separated if more than one) |
| `CORS_ORIGIN_REGEX` | Recommended | Matches Vercel preview URLs automatically — see above |
| `DATABASE_URL` | Yes | Neon pooled connection string, `postgresql+asyncpg://...` |
| `DATABASE_URL_SYNC` | Yes | Same, `postgresql+psycopg2://...?sslmode=require` (used by Alembic) |
| `DATABASE_SSL` | Yes | `true` for Neon |
| `LLM_PROVIDER` | Yes | `mock` to run with no AI credentials, or `grok`/`deepseek`/`openai`/`anthropic`/`custom` |
| `LLM_MODEL` | If not mock | e.g. `grok-4-latest` |
| `LLM_API_KEY` | If not mock | Provider's API key |
| `LLM_API_BASE` | Only for `custom` | Any OpenAI-compatible endpoint |
| `RUMIA_DB_MODE` | No | `disabled` until Rumia grants access |
| `RUMIA_DATABASE_URL` | Only if enabled | Read-only, listings-only |
| `STORAGE_PROVIDER` | Yes | `s3` recommended in production (see note below) |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION` | If `s3` | Any S3-compatible provider |
| `RATE_LIMIT_CHAT_PER_MINUTE`, `RATE_LIMIT_DEFAULT_PER_MINUTE` | No | Defaults are `20`/`60` |

**Storage note:** `STORAGE_PROVIDER=local` writes past-paper/complaint-attachment files to the container's own disk. On Railway/Render that disk is ephemeral by default (wiped on every redeploy), so switch to `STORAGE_PROVIDER=s3` for anything beyond a quick demo — any S3-compatible bucket works (Cloudflare R2 and Backblaze B2 both have generous free tiers if you don't already have one).

### Database (Neon dashboard, not app env vars)

Nothing to configure beyond creating the project — Neon gives you the connection strings directly.

## DevOps checklist (what's actually required to go live)

- [ ] Neon project created, pooled connection string copied
- [ ] `alembic upgrade head` run once against Neon
- [ ] `python -m app.scripts_entry seed --if-empty` run once against Neon (skip if you're seeding your own real data instead of the demo dataset)
- [ ] Backend deployed (Railway/Render/Fly.io) from `backend/Dockerfile`, all env vars above set, `SECRET_KEY` is a real random value (not the dev default)
- [ ] Backend health check passes: `curl https://<backend-url>/api/health` returns `{"status": "ok", ...}`
- [ ] `STORAGE_PROVIDER` set to `s3` (or accepted as ephemeral for a demo)
- [ ] Frontend deployed on Vercel with `VITE_API_URL` pointed at the backend
- [ ] Backend's `CORS_ORIGINS`/`CORS_ORIGIN_REGEX` updated to allow the real Vercel domain(s)
- [ ] End-to-end smoke test against the live URLs: register, log in, send a chat message, confirm the SSE trace streams and a final answer arrives
- [ ] `LLM_PROVIDER` decided: `mock` is a legitimate production choice if no AI credential is available yet; otherwise `grok`/`deepseek`/`openai`/`anthropic`/`custom` with a real key
- [ ] No `.env` file committed anywhere (`.gitignore` already excludes it - only `.env.example` should be tracked)

## Rollback and redeploys

- **Frontend:** Vercel keeps every previous deployment; "Promote to Production" on an older one is an instant rollback.
- **Backend:** redeploy the previous image/commit on Railway/Render/Fly.io; the database is untouched by a backend rollback since migrations are additive and run separately.
- **Database:** Neon supports point-in-time restore from its dashboard if a bad migration ever needs undoing - a backend rollback alone does not undo a schema change, so treat migrations as forward-only in the same spirit as `docs/DEPLOYMENT.md`.
