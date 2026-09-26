# Deployment

Omniscient runs as a single isolated stack on one Oracle Compute instance.
It shares nothing with Rumia: not a database, not a container, not a
process. Restarting or redeploying Omniscient cannot take Rumia down, and
vice versa.

```
omniscient.co.ke
│
└── Oracle Compute (VM.Standard.A1.Flex, 2 OCPU / 12 GB)
    │
    ├── caddy       TLS termination, the only published ports (80/443)
    ├── frontend    static SPA, served by nginx
    ├── backend     FastAPI/uvicorn, runs migrations on boot
    └── db          PostgreSQL 16 + pgvector
                     │
                     └── past_paper_chunks (vector(384), HNSW index)

Cloudflare R2   past-paper PDFs and complaint attachments
Cloudflare DNS  omniscient.co.ke → the instance
```

---

## Cost, and why the instance is sized the way it is

This is the part worth reading before changing anything about the shape.

Oracle halved the Always Free Ampere A1 allowance on **2026-06-15**, from
4 OCPU / 24 GB to **2 OCPU / 12 GB**, and began terminating oversized
instances on **2026-08-18**. The free allowance is now 1,500 OCPU-hours
and 9,000 GB-hours per month.

A1 pricing is **$0.01/OCPU-hour + $0.0015/GB-hour**, and the Always Free
allowance still applies on a Pay As You Go account — you are only charged
above it. So a 2 OCPU / 12 GB A1 costs **nothing**:

| Resource | Monthly usage | Free allowance | Bill |
|---|---|---|---|
| A1 OCPU | 2 × 730 = 1,460 h | 1,500 h | $0 |
| A1 memory | 12 × 730 = 8,760 GB-h | 9,000 GB-h | $0 |
| Block volume | ≤ 200 GB | 200 GB | $0 |
| Outbound data | ~0 GB | 10 TB | $0 |

The instance this replaced was `VM.Standard.E5.Flex` at 1 OCPU / 12 GB,
which cost **~$39/month** and got none of the allowance, because the free
tier only covers A1 and E2.1.Micro. Moving to A1 saves roughly **$475 a
year** and doubles the available CPU. The memory line is unchanged in
size, which is why the saving is that large.

### Migrating an existing x86 instance to A1

You **cannot** resize a shielded instance — Oracle's own documentation is
that when you edit one, only its name can be changed, and shielded
instances support neither live nor reboot migration. And you cannot reuse
its boot volume, because an x86 kernel does not boot on Ampere.

So this is a create-new-then-migrate, not a resize. The order matters,
and not only for convenience: **A1 capacity is frequently exhausted in a
region.** Deleting first and then failing to create an A1 leaves you with
no instance at all.

The scripts are in `infra/oci/`, and each is safe to read before running.

| Script | Runs from | What it does |
|---|---|---|
| `preflight.sh` | your machine, with the OCI CLI | Read-only checks: home region, A1 capacity, reserved-vs-ephemeral IP, block-volume budget, arm64 CI status |
| `provision-a1.sh` | your machine, with the OCI CLI | Creates the A1 in the **same compartment, AD and subnet**; prints the command and asks before creating anything |
| `backup-from-old.sh` | the **old** instance | `pg_dump`, the `.env` file, row counts, and a restore write-up |
| `restore-on-new.sh` | the **new** instance | Restores the dump and verifies it against those row counts |

Two things the preflight exists to catch:

- **Is your region the home region?** The A1 free allowance applies
  *only* in the tenancy's home region. An A1 created elsewhere is billed
  in full — roughly $28/month for 2 OCPU / 12 GB — with no credit against
  the allowance.
- **Is 84.12.101.132 reserved or ephemeral?** A reserved IP can be
  released from the old instance and attached to the new one, so DNS and
  the `VM_HOST` secret need no change at all. An ephemeral IP disappears
  with the instance and you get a new one.

```bash
# 1. Read-only checks
bash infra/oci/preflight.sh omniscient-instance

# 2. Capture what matters, on the old instance, BEFORE deleting it
ssh -i ssh-key-2026-09-26.key ubuntu@84.12.101.132 'bash -s' < infra/oci/backup-from-old.sh
# Copy it OFF the instance. A bundle left on the machine you are about to
# terminate is not a backup. (remote -> local, so it is host:path first)
mkdir -p /tmp/omniscient-migration
scp -r -i ssh-key-2026-09-26.key ubuntu@84.12.101.132:~/omniscient-migration-* /tmp/omniscient-migration/

# 3. Create the replacement
bash infra/oci/provision-a1.sh

# 4. Bootstrap and restore on the new instance
ssh -i ssh-key-2026-09-26.key ubuntu@<new-ip> 'sudo bash -s' < infra/deploy/bootstrap.sh
# Copy the bundle to the new instance, then restore into it
scp -r -i ssh-key-2026-09-26.key /tmp/omniscient-migration/omniscient-migration-* ubuntu@<new-ip>:~/
ssh -i ssh-key-2026-09-26.key ubuntu@<new-ip> 'bash -s' < infra/oci/restore-on-new.sh

# 5. Point DNS (or attach the reserved IP), then verify
curl -fsS https://omniscient.co.ke/api/health

# 6. Only now
oci compute instance terminate --instance-id <old-ocid>
```

Step 2 is the one that cannot be undone. `docker-compose` keeps Postgres
in a **named volume inside the container filesystem on the boot volume**,
so terminating the instance destroys the database. Past papers and
complaint attachments are safe in R2, and the code is safe in git — but
`.env` is gitignored and therefore exists nowhere else. `backup-from-old.sh`
copies it into the bundle and prints a reminder, because a copy on the
machine you are about to destroy is not a backup.

Two more things worth knowing:

- **Release the reserved IP before creating the new instance.** The A1
  launch will fail while the IP is still attached. Detach only the VNIC —
  `oci compute instance action terminate-vnics` — which leaves the old
  instance running.
- **Deleting the instance does not delete its boot volume**, so an
  orphaned volume keeps accruing storage charges against your 200 GB
  free allowance. Terminate the volume explicitly once you are satisfied.

Things that will quietly cost money, and how this setup avoids them:

- **Do not exceed 2 OCPU / 12 GB.** Going to 4/24 is ~$27/month more, and
  sizing above the free allowance is what triggers reclamation.
- **Keep the boot volume at or under 200 GB.** Block storage beyond the
  allowance is billed per GB-month. Images are multi-arch, so budget
  accordingly and rely on the `docker image prune` in the deploy script.
- **Serve files from R2, not the instance.** Every PDF the backend would
  otherwise stream out of the VM is OCI egress. R2 egress is free, so
  this keeps the instance's outbound traffic at effectively zero.
- **Do not put a load balancer in front of this.** OCI Load Balancer is
  billed per hour *and* per GB. Caddy on the same instance does the same
  job for nothing, and at this traffic level a single instance has no
  need for one.
- **Keep one backend replica.** The rate limiter is in-process (see
  [Scaling](#scaling-and-the-things-that-break-first)), so extra
  replicas multiply the effective rate limit.

### A known risk, accepted

Oracle reclaims Always Free compute that is idle over a 7-day window
(95th-percentile CPU, network and memory all below 20%). A low-traffic
student app can trip this. This deployment does not currently defend
against it, by choice. If the instance is reclaimed, the recovery is:

1. Recreate the A1 instance and re-attach its boot volume, or create a
   fresh one.
2. Re-run `infra/deploy/bootstrap.sh`.
3. Restore `.env` (it lives only on the VM — see [Secrets](#secrets)).
4. `docker compose -f docker-compose.yml up -d`.

The database survives a reboot because it is on a named volume, not in
the container. To defend against reclamation instead, run a cheap
scheduled job that makes a real request every few hours.

---

## One-time setup

### 1. Size the instance

Create a **VM.Standard.A1.Flex** with **2 OCPUs and 12 GB** in your home
region, with a boot volume of 100–150 GB. Use an Ubuntu 22.04+ or Oracle
Linux image, public subnet, and assign the public IP.

### 2. DNS

Point `omniscient.co.ke` (and `www`, which Caddy redirects to the apex)
at the instance's public IP. If the records are proxied through
Cloudflare, see the note in `infra/caddy/Caddyfile` about the HTTP-01
challenge — Caddy cannot complete a Let's Encrypt validation against a
Cloudflare proxy without a DNS challenge.

### 3. Open ports

In the VCN security list and any NSG on the VNIC:

| Port | Source | Purpose |
|---|---|---|
| 22 | your IP only | SSH |
| 80 | 0.0.0.0/0 | ACME challenge + redirect to HTTPS |
| 443 | 0.0.0.0/0 | HTTPS |

Nothing else. The database and the API are not published to the host at
all — see `docker-compose.yml`.

### 4. Bootstrap

```bash
ssh -i ssh-key-2026-09-26.key ubuntu@84.12.101.132 'sudo bash -s' < infra/deploy/bootstrap.sh
```

This installs Docker and the Compose **plugin** (not the v1
`docker-compose` binary — the deploy script needs `--wait`), installs
`poppler-utils` for PDF work, caps the Docker log size, creates an
unprivileged `omniscient` user in the `docker` group, and clones the repo
to `/opt/omniscient`. It is safe to re-run; every step checks first.

It deliberately does **not** start the stack. Starting it without real
credentials produces a crash-looping container and a confusing first
migration failure.

### 5. Configure

```bash
sudo -u omniscient cp /opt/omniscient/.env.example /opt/omniscient/.env
sudo -u omniscient chmod 600 /opt/omniscient/.env
sudo -u omniscient nano /opt/omniscient/.env
```

Minimum required values:

| Variable | Notes |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Strong random password |
| `SECRET_KEY` | `openssl rand -hex 32`. Rotating it logs everyone out. |
| `LLM_PROVIDER` | `deepseek` |
| `LLM_MODEL` | `deepseek-flash`. `deepseek-chat` and `deepseek-reasoner` were retired 2026-07-24. |
| `LLM_API_KEY` | DeepSeek key |
| `LLM_FALLBACK_PROVIDER` | `groq` |
| `LLM_FALLBACK_MODEL` | `openai/gpt-oss-20b` (see note) |
| `LLM_FALLBACK_API_KEY` | Groq key |
| `STORAGE_PROVIDER` | `s3` |
| `S3_ENDPOINT` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | From the R2 dashboard |
| `S3_ADDRESSING_STYLE` | Must be `path` for R2 |
| `S3_PUBLIC_URL` | `https://files.omniscient.co.ke` |
| `EMBEDDING_ENABLED`, `RAG_ENABLED` | `true` |
| `ACME_EMAIL` | Let's Encrypt contact address |

**Do not use `llama-3.3-70b-versatile` for the Groq fallback.** Groq shut it
down on 2026-08-16, and it was an Enterprise-tier model that was never on
the free developer plan. `openai/gpt-oss-20b` is the current
production-tier default on Groq: ~1000 tokens/sec, 250K TPM / 1K RPM on
the free plan, and $0.075 in / $0.30 out per million tokens. It is also a
genuine fallback rather than a token one — different vendor, different
inference stack.

### 6. Cloudflare R2

1. Create a bucket.
2. Attach a custom domain (e.g. `files.omniscient.co.ke`) and set
   `S3_PUBLIC_URL` to it.
3. Decide on bucket visibility. Past papers should be public; complaint
   attachments contain student PII and should use a separate private
   bucket — which this codebase does **not** yet support, because
   `url_for` returns unsigned URLs. Until that is added, keep
   `STORAGE_PROVIDER=local` if you need private attachments, and accept
   that the files live on the instance volume.
4. Create an R2 API token with Object Read & Write on that bucket.

### 7. First deploy

```bash
cd /opt/omniscient
sudo -u omniscient docker compose up -d
sudo -u omniscient docker compose ps
curl -fsS https://omniscient.co.ke/api/health
```

Then build the search index:

```bash
sudo -u omniscient docker compose exec backend \
  python -m app.scripts_entry reindex-past-papers
```

---

## CI/CD

Two workflows, both in `.github/workflows/`.

### `ci.yml` — on every push and PR

| Job | What it proves |
|---|---|
| `backend` | `ruff check` and the pytest suite |
| `frontend` | `oxlint`, `tsc -b`, `vitest`, and a real production build |
| `migrations` | Alembic applies to a real PostgreSQL + pgvector, the extension and HNSW index exist afterwards, exactly one head, and the whole chain downgrades and re-upgrades |
| `arm64-build` | The backend image builds **and its embedding model downloads** for `linux/arm64` |

The `arm64-build` job is the one that makes the A1 migration safe. The
biggest deployment risk of moving to ARM is an `onnxruntime` or base-image
wheel that does not exist for `aarch64`; the backend Dockerfile downloads
the embedding model at build time specifically so that failure surfaces
here rather than as a reindex that silently produces nothing in
production.

The `migrations` job exists because a migration can be valid Python and
still be invalid SQL. `CREATE EXTENSION vector` and `CREATE INDEX ... USING
hnsw` are only verifiable against a real server.

### `deploy.yml` — on a `v*` tag, or manually

1. Builds both images for `linux/amd64,linux/arm64`, pushes to GHCR with
   provenance and an SBOM, tagged both with the version and `latest`.
2. SSHes into the VM and runs `infra/deploy/deploy.sh`, which pulls
   first, then `docker compose up -d --wait`. `--wait` blocks until every
   container is healthy, and on failure the script reads the image the
   *running* container reports and rolls back to it.
3. Smoke-tests the public URL: `/api/health`, the SPA shell, and that
   `rag_enabled` is true.

Deploys are serialised by a `concurrency` group. Two overlapping
deploys would otherwise restart the same containers against each other
mid-migration.

### GitHub Secrets required

Set these under **Settings → Secrets and variables → Actions**. None of
them belong in the repository.

| Secret | Value |
|---|---|
| `VM_HOST` | `84.12.101.132` |
| `VM_SSH_PORT` | `22` |
| `VM_USER` | `ubuntu` (Ubuntu image) or `opc` (Oracle Linux) |
| `VM_SSH_KEY` | The **contents** of `ssh-key-2026-09-26.key` |
| `VM_HOST_FINGERPRINT` | `SHA256:1TdzE0B3ho1qDVgzQuY4k8lHaGvDaf8yhcYzv/oDa0E` (see below) |

The deploy keypair lives at the repository root:

```
ssh-key-2026-09-26.key       private — NEVER committed, never pasted anywhere public
ssh-key-2026-09-26.key.pub   public  — injected into the instance at launch
```

Both are excluded by `.gitignore` (`*.key` and `*.pub`).

**The private key must be mode 600.** SSH silently refuses anything more
permissive, with an "UNPROTECTED PRIVATE KEY FILE" warning that scrolls
past and leaves the symptom looking like a wrong-password error:

```bash
chmod 600 ssh-key-2026-09-26.key
```

`provision-a1.sh` sets this for you and verifies the two halves actually
match before it launches anything, so a mismatched pair fails before an
instance exists rather than as a wall of rejected logins.

To get the host key fingerprint, and to confirm it out of band before
trusting it:

```bash
ssh-keyscan -p 22 84.12.101.132 2>/dev/null | ssh-keygen -lf -
```

`84.12.101.132` (Ubuntu 22.04, OpenSSH 8.9p1) presents three host keys.
Only the ed25519 one is negotiated by a modern client, so that is the
value to pin:

| Type | Fingerprint |
|---|---|
| **ed25519** (negotiated) | `SHA256:1TdzE0B3ho1qDVgzQuY4k8lHaGvDaf8yhcYzv/oDa0E` |
| rsa | `SHA256:l0AV2hfXBiFpwiyzvoTxDkvu3tte3L/VbVSNNT8RXM4` |
| ecdsa | `SHA256:JK/iqyVC0SKprDwSu2rPozB8a/FYuYCDos1llgBWZCI` |

To confirm which one a real connection picks:

```bash
ssh -vv -o BatchMode=yes ubuntu@84.12.101.132 true 2>&1 | grep 'Server host key'
# debug1: Server host key: ssh-ed25519 SHA256:1TdzE0B3ho...
```

`ssh-keyscan` is unauthenticated — it tells you what the host *claims*,
which is exactly why the value above is recorded here and in the secrets
table. If a future `ssh -vv` reports a different fingerprint, the host
was rebuilt or replaced and the deploy key is being offered to something
you did not expect. Investigate before updating the secret.

Without pinning it at all, a machine-in-the-middle can silently receive
the deploy key.

Add the matching **public** key to `~<user>/.ssh/authorized_keys` on the
instance. `provision-a1.sh` does this at launch via `--metadata`, so it is
usually already done — the manual step is only for a host you built by
hand.

The keypair above was generated on 2026-09-26 as an RSA-2048 key. It is
fine for this, but if you ever regenerate, prefer `ed25519`:

```bash
ssh-keygen -t ed25519 -f ssh-key-<date>.key -N ''
```

### Branch and release policy

`main` is the source of truth. The repository's default branch is `main`,
`infra/deploy/bootstrap.sh` clones `--branch main`, and
`infra/oci/provision-a1.sh` expects to read `main`.

Deployment is **not** tied to a branch. It is triggered by pushing a
`v*` tag, so the only way to deploy is to release an intentional,
numbered version:

```
main ──commit──► CI (must be green) ──tag──► Deploy ──► 84.12.101.132
```

A commit to `main` runs CI and stops there. Nothing reaches production
until a tag exists, which means there is no such thing as an accidental
production deploy from a branch push — the most common way a small team
sends unreviewed code live.

Concretely:

```bash
git checkout main
git pull --ff-only
# ... work, reviewed, CI green ...
git push origin main

# release
git tag v1.0.0 && git push origin v1.0.0
```

Do not tag a commit whose CI has not passed, and do not move a tag that
has already been deployed — the deploy job is serialised, but a retagged
version still deploys, and there is no "un-release".

### Deploying

```bash
git tag v1.0.0 && git push origin v1.0.0
```

or, from the Actions tab, run **Deploy** with `workflow_dispatch` and
optionally an `image_tag`. A manual run is tagged with the commit SHA
rather than a version name, so it can never be mistaken for a release.

---

## Secrets

There are no secrets in this repository, and the pipeline is built so
there are none in its history either.

- The deploy job receives an SSH key and nothing else. Every real
  credential — DeepSeek, Groq, R2, `SECRET_KEY`, the database password —
  lives in `/opt/omniscient/.env` on the VM, written once by an operator
  and never read, written, or logged by CI.
- `.env` is gitignored, as are the common variants (`*.env.bak`,
  `*.key`, `*.pem`, `id_rsa*`, and so on) so a stray copy is still
  excluded.
- `backend/.env` is a **symlink to the repo-root `.env`**, which is why
  the test suite sets `OMNISCIENT_ENV_FILE=` to switch dotenv loading off.
  See [Testing](#testing-and-the-env-file-trap).

**Losing the VM means losing `.env`.** Nothing else in the stack depends on
it, but those keys are not recoverable from the repository. Keep a copy in
a password manager.

---

## Migrations

`alembic upgrade head` runs on backend boot, before uvicorn starts. Alembic
takes an advisory lock, so if you ever run more than one replica, they
serialise instead of racing. The app does not serve traffic until the
schema is at head, which is what stops a deploy from serving 500s against
a half-migrated database.

Generate new revisions locally against a dev database, review the SQL, and
commit them:

```bash
cd backend
alembic revision --autogenerate -m "add something"
```

Never hand-edit the production schema.

### Changing the embedding model or `EMBEDDING_DIMENSIONS`

These are a matched pair and changing one without the other makes search
return **nonsense silently** — no error, just bad answers.

1. Write a migration that resizes the column:
   `ALTER TABLE past_paper_chunks ALTER COLUMN embedding TYPE vector(N) USING ...`
2. Update `VECTOR_DIMENSIONS` in `app/db/vector.py` **and**
   `EMBEDDING_DIMENSIONS` in `.env`.
3. Update `EMBEDDING_MODEL`.
4. Re-embed everything: `reindex-past-papers --force`.

The `EmbeddingService` refuses to write vectors whose width disagrees with
the configured dimension, so a mismatch surfaces as a clear error rather
than a corrupt index.

---

## Operations

### Health

```bash
curl -fsS https://omniscient.co.ke/api/health
```

Reports the active provider, the fallback, the storage provider, and
whether RAG and embeddings are on. Each container also has its own
Docker healthcheck, which is what `docker compose up --wait` gates on.

### Logs

```bash
docker compose logs -f backend
```

The backend logs structured JSON in production. Every line carries a
correlation id, and `X-Request-ID` is echoed on the response so a
student-reported failure can be traced. Secrets, tokens and conversation
content are redacted by `core/logging.py` before anything is written.

Logs rotate at 10 MB × 3 per container, and the Docker daemon has its own
cap, because an unbounded log is the most common way to fill a small boot
volume.

### Reindexing

```bash
# Only new or previously-failed papers. Cheap and idempotent.
docker compose exec backend python -m app.scripts_entry reindex-past-papers

# Everything, including papers already indexed.
docker compose exec backend python -m app.scripts_entry reindex-past-papers --force

# One paper.
docker compose exec backend python -m app.scripts_entry reindex-past-papers --paper-id <uuid>
```

Or from the admin UI, under **Past papers**. Both hit the same service.

A paper that fails to index does not abort the run; each paper commits
independently and failures are reported at the end. The most common cause
is a **scanned PDF with no text layer** — these are rejected with a clear
message rather than indexed as an empty, permanently-unsearchable paper.
Run OCR on those first.

### Rolling back

The deploy script does this automatically when a rollout fails. To do it
by hand:

```bash
cd /opt/omniscient
PREV=$(docker inspect --format '{{.Config.Image}}' $(docker compose ps -q backend))
BACKEND_IMAGE=$PREV FRONTEND_IMAGE=${PREV/backend/frontend} \
  docker compose up -d --wait
```

The database is on a separate volume, so a code rollback never touches
data. Rolling a *migration* back is a separate, deliberate decision —
`alembic downgrade -1` — and is only safe if the previous code tolerates
the previous schema.

---

## Scaling, and the things that break first

At this size one instance is the right answer; do not add Kubernetes.

If you outgrow it, in this order:

1. **The rate limiter is in-process** (`core/rate_limit.py`). A second
   replica means each enforces the limit independently, so the effective
   cap doubles. Move it to Redis before adding replicas.
2. **The reindex job state is in-process** (`services/reindex_job.py`).
   With more than one replica, a reindex started on one is invisible to
   the others and two can run at once. Use a Postgres advisory lock or a
   Redis flag.
3. **`uvicorn` runs a single worker** for the same reason. Scale with
   replicas, not workers.
4. **Storage must be S3 before you add replicas** — local disk is not
   shared between them. This deployment already uses R2.
5. **Embeddings are computed in-process.** On a bigger box, switch
   `EMBEDDING_BACKEND=tei` and run a Text Embedding Inference sidecar; no
   application code changes.

### Idle reclamation

See [Cost](#cost-and-why-the-instance-is-sized-the-way-it-is). Currently
unmitigated, by choice.

---

## Testing, and the `.env` trap

The suite pins every variable it depends on through the process
environment, which pydantic-settings gives precedence over any dotenv
file. `OMNISCIENT_ENV_FILE=` (empty) disables dotenv loading entirely.

This matters more than it sounds. `backend/.env` is a **symlink to the
repo-root `.env`**, and the app reads a dotenv file relative to the
working directory. Before this was fixed, a developer with
`RUMIA_DB_MODE=enabled` locally had the housing tests silently call the
**live Rumia API** and assert against Rumia's listings instead of their
own fixtures. The guard that was supposed to prevent this —
mutating `Settings.model_config["env_file"]` — does not work on
pydantic-settings 2.7.x, because the dotenv source is built from the
config captured at class-creation time.

```bash
cd backend
ruff check .
OMNISCIENT_ENV_FILE= pytest -q
```

Lint is `ruff check` only. `ruff format` is deliberately not part of the
workflow: this codebase was never formatted with it, and adopting it now
would bury any real change under a several-hundred-line reformat diff.

### Verifying Docker builds

The Dockerfiles are exercised in CI, including the arm64 leg. To check
locally:

```bash
docker compose -f docker-compose.dev.yml build
```

The original note in this document about Docker Hub rate limits blocking
verification in a sandbox no longer applies; the builds run in CI on every
push.

---

## Local development

```bash
cp .env.example .env      # then set APP_ENV=development, LLM_PROVIDER=mock
docker compose -f docker-compose.dev.yml up -d --build
```

`docker-compose.yml` is **production**; `docker-compose.dev.yml` is local
and differs deliberately: images build from source, demo data is seeded on
first boot, the database and API are published to localhost, and there is
no TLS terminator. Both run PostgreSQL with pgvector so retrieval behaves
identically in both.
