# Deployment

## Target shape (Oracle Cloud)

Omniscient is designed to run as its own isolated stack, fully separate from Rumia:

```
Oracle Cloud
│
├── Rumia                     (existing, untouched)
│   └── existing services / database
│
└── Omniscient                (this repo)
    ├── frontend   (static build, served by nginx)
    ├── backend    (FastAPI/uvicorn)
    └── PostgreSQL (Omniscient's own instance)
```

Omniscient never shares Rumia's database, application container, or process. Restarting or redeploying Omniscient cannot take Rumia down, and vice versa.

## Recommended setup: a single Compute VM + Docker Compose

For a workload this size, one Oracle Cloud Compute instance running the provided `docker-compose.yml` is the right amount of infrastructure — see the brief's own instruction against over-engineering with Kubernetes/microservices for a small team's product.

1. Provision an Oracle Cloud Compute VM (Ampere A1 or a small x86 shape is enough), Ubuntu 22.04+, with Docker and the Compose plugin installed.
2. Open the VM's security list / network security group for ports `80`/`443` (frontend) and optionally `8000` if the API should be reachable directly (otherwise keep it internal and let the frontend proxy to it).
3. Clone this repository onto the VM.
4. Copy `.env.example` to `.env` and fill in real values:
   - `SECRET_KEY` — a long random string (`openssl rand -hex 32`).
   - `DATABASE_URL` / `DATABASE_URL_SYNC` — point at the `db` service (already set correctly in `docker-compose.yml` for the bundled Postgres container) or an Oracle-managed Postgres instance if preferred.
   - `LLM_PROVIDER=anthropic`, `LLM_MODEL`, `LLM_API_KEY` — once a real Anthropic key is available. Leave `LLM_PROVIDER=mock` to run without one; the product remains fully usable.
   - `RUMIA_DB_MODE` / `RUMIA_DATABASE_URL` — leave `disabled` until Rumia grants a read-only, listings-only connection string. See the Rumia section in the root README.
   - `STORAGE_PROVIDER` — `local` is fine for a single VM; switch to `s3` with Oracle Cloud Object Storage's S3-compatible endpoint for durability across redeploys.
5. `docker compose up -d --build`. The backend container runs Alembic migrations and seeds demo data on first boot (`alembic upgrade head && python -m app.scripts_entry seed --if-empty`), then starts uvicorn.
6. Put a reverse proxy / TLS terminator in front (Oracle Cloud's Load Balancer, or a lightweight Caddy/nginx container) once a domain is attached — this repo intentionally does not hardcode a specific TLS setup, since the domain and certificate strategy are an operator decision.

## Building images

`backend/Dockerfile` and `frontend/Dockerfile` are both standard, minimal, non-root, multi-stage-where-it-matters builds — read them directly, they're short and commented. Two things worth knowing:

- The frontend image bakes `VITE_API_URL` in at build time (`docker build --build-arg VITE_API_URL=https://api.yourdomain.example ...` or the `args:` block in `docker-compose.yml`), because Vite inlines `import.meta.env.*` into the built JS bundle — there is no runtime env injection for a static SPA build. Rebuild the frontend image if the backend's public URL changes.
- Neither Dockerfile needs any OS packages beyond the base image (`asyncpg` and `psycopg2-binary` both ship self-contained wheels), which keeps the build fast and avoids needing `apt-get`/network access to a Debian mirror during the image build.

**Note on this sandbox**: while building this project, live `docker build` verification was blocked in the development sandbox by Docker Hub's anonymous-pull rate limit on the sandbox's shared egress IP (`429 Too Many Requests` resolving `python:3.11-slim`, `node:22-alpine`, and even `alpine:latest` — confirmed to be Docker Hub's own limit, not a proxy/network policy issue here). This is a property of the sandbox's shared IP, not of Oracle Cloud or any normal CI/deploy environment, which will pull those images without issue. The Dockerfiles were reviewed manually for correctness instead; re-verify with `docker compose build` in a normal environment before first production deploy.

## Database migrations in production

Never hand-edit the production schema. Ship a new Alembic revision (`alembic revision --autogenerate -m "..."` locally against a dev database, review the generated script, commit it) and let `alembic upgrade head` (already wired into the backend container's startup command) apply it on deploy.

## Scaling notes

- The rate limiter in `core/rate_limit.py` is in-process/in-memory, which is correct for a single backend instance. If Omniscient is later scaled to multiple backend instances, back it with Redis instead of changing the approach.
- `STORAGE_PROVIDER=s3` (Oracle Cloud Object Storage, S3-compatible) is the right choice once running more than one backend instance, since local disk storage wouldn't be shared across them.

## Rolling back

`docker compose down && git checkout <previous-tag> && docker compose up -d --build` is sufficient at this scale. Keep the database on a separate, persistent volume (already configured via the `omniscient_db_data` named volume) so a rollback of application code never touches data.
