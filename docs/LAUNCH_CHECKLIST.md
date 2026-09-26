# Launch checklist

Everything between "the code is written" and "omniscient.co.ke serves
traffic", in dependency order. Tick as you go.

**Status of the code right now:** 189 backend tests, 104 frontend tests,
ruff clean, both compose files valid, frontend builds. The application
code is done. None of it is committed, deployed, or reachable.

---

## Phase 1 — Get credentials

Nothing else can start until these exist. Do them in parallel; each is
an independent sign-up.

### 1.1 DeepSeek API key (the primary LLM)

- Sign in at <https://platform.deepseek.com>
- **Add credit.** DeepSeek's API is prepaid — a key with a zero balance
  authenticates successfully and then fails every request, which looks
  exactly like a broken deployment.
- Create a key under **API Keys**.
- Models: `deepseek-flash` (default here) or `deepseek-v4-pro`.
  Do **not** use `deepseek-chat` or `deepseek-reasoner`; both were
  retired on 2026-07-24.

### 1.2 Groq API key (the fallback)

- Sign in at <https://console.groq.com/keys>
- Create a key. The free developer plan is enough.
- Model: `openai/gpt-oss-20b`. **Not** `llama-3.3-70b-versatile` — Groq
  shut it down on 2026-08-16, and it was Enterprise-tier anyway.

### 1.3 Cloudflare R2 bucket

- <https://dash.cloudflare.com> → **R2** → **Create bucket**
- A payment method must be on the Cloudflare account before R2 buckets
  can be created. The free tier is 10 GB storage, 1M writes and 10M
  reads per month, so this should cost nothing at your volume.
- Create an **R2 API token** (R2 → Manage API tokens → Create) with
  **Object Read & Write** scoped to that bucket only. You need three
  values from it: Access Key ID, Secret Access Key, and the S3 endpoint
  containing your account ID.
- **Attach a custom domain**: R2 → bucket → Settings → Custom Domains →
  `files.omniscient.co.ke`. Cloudflare creates the DNS record for you.
- Set bucket visibility. Past papers are fine public. **Complaint
  attachments contain student PII** — read the note in 1.4 before
  choosing one bucket for both.

### 1.4 Decide the attachment situation (read this)

`url_for()` returns an **unsigned** URL, so with a single public bucket,
complaint attachments are world-readable to anyone who can guess or
obtain the URL. For past papers that is fine and intended. For student
complaints it is not.

Three options, in order of preference:

1. **Two buckets, and accept that complaint attachments are public
   until presigned URLs exist.** Fine only if you are not yet taking real
   complaints.
2. **Keep `STORAGE_PROVIDER=local` for now.** Attachments live on the VM
   and are served only through authenticated API routes. Cost: files are
   lost if the VM is replaced, and they consume block volume.
3. **Add presigned-URL support before going live.** Roughly a day of
   work: sign `get_object` with an expiry in `S3StorageBackend` and stop
   returning bare URLs.

Past-paper search does not need attachments to be public, so option 2 or 3
keeps RAG fully functional either way.

### 1.5 GitHub Actions secrets

Already reported as done, but the workflows do not exist on the remote
yet, so nothing consumes these until Phase 3. Re-check the list in
[`DEPLOYMENT.md`](DEPLOYMENT.md#github-secrets-required):

`VM_HOST` (`84.12.101.132`) · `VM_SSH_PORT` (`22`) · `VM_USER` ·
`VM_SSH_KEY` (contents of `ssh-key-2026-09-26.key`) ·
`VM_HOST_FINGERPRINT` (`SHA256:1TdzE0B3ho1qDVgzQuY4k8lHaGvDaf8yhcYzv/oDa0E`)

---

## Phase 2 — DNS and firewall

### 2.1 DNS

`omniscient.co.ke` **does not currently resolve.** Until it does, Caddy
cannot obtain a certificate and nothing is reachable.

| Record | Value |
|---|---|
| `omniscient.co.ke` | A → `84.12.101.132` |
| `www.omniscient.co.ke` | A → `84.12.101.132` (Caddy redirects to the apex) |
| `files.omniscient.co.ke` | created for you by R2 in 1.3 |

If the records are **proxied** (orange cloud), Caddy's HTTP-01
certificate challenge cannot complete. Either set them to DNS-only, or
switch the Caddyfile to a DNS-01 challenge — it documents the
`dns cloudflare` block.

### 2.2 Firewall

Currently **only port 22 is open**, and 22 is open to the entire
internet.

- **80 and 443** must be reachable for TLS and ACME.
- **22** should be restricted to your own IP.

Decide the isolation mechanism first — see
[`DEPLOYMENT.md`](DEPLOYMENT.md#migrating-an-existing-x86-instance-to-a1)
and confirm whether Omniscient shares a subnet with Rumia. Short version:
a **VNIC NSG** cannot affect Rumia; a **subnet security list** can, if
you share a subnet.

---

## Phase 3 — Push the code

Do this before touching the VM, because CI is what proves the ARM build
works.

1. Finish your in-flight UI work.
2. Commit and push to `main`. `main` is the default branch; `infra/`
   clones `--branch main`.
3. Wait for **CI** to go green. Pay attention to the job called
   **`Backend image builds on arm64`** — it builds the backend image for
   `linux/arm64` and bakes the embedding model, which is the only way to
   find out ahead of time that `onnxruntime` has no aarch64 wheel. If
   that job fails, stop and fix it before deploying.
4. Nothing deploys on its own. Deployment happens when you push a `v*`
   tag, so tagging is the "go live" button — see Phase 6.

---

## Phase 4 — Provision the VM

`84.12.101.132` is running Ubuntu 22.04 and is otherwise bare: no Docker,
no application, and the deploy key is **not** in `authorized_keys` (a
login attempt returns `Permission denied (publickey)`).

```bash
# 1. Install the deploy public key, if the instance was built by hand
ssh-copy-id -i ssh-key-2026-09-26.key.pub ubuntu@84.12.101.132

# 2. Install Docker + the Compose plugin, clone the repo, create the
#    unprivileged deploy user
ssh -i ssh-key-2026-09-26.key ubuntu@84.12.101.132 'sudo bash -s' \
  < infra/deploy/bootstrap.sh
```

`bootstrap.sh` will not start the stack, deliberately — starting it
without real credentials produces a crash-looping container.

---

## Phase 5 — Configure and start

### 5.1 Create `.env`

```bash
sudo -u omniscient cp /opt/omniscient/.env.example /opt/omniscient/.env
sudo -u omniscient chmod 600 /opt/omniscient/.env
sudo -u omniscient nano /opt/omniscient/.env
```

Minimum values to fill in:

```bash
APP_ENV=production
APP_URL=https://omniscient.co.ke
API_URL=https://omniscient.co.ke
CORS_ORIGINS=https://omniscient.co.ke,https://www.omniscient.co.ke
SECRET_KEY=<openssl rand -hex 32>

POSTGRES_USER=omniscient
POSTGRES_PASSWORD=<strong random>
POSTGRES_DB=omniscient

LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-flash
LLM_API_KEY=<deepseek key>
LLM_FALLBACK_PROVIDER=groq
LLM_FALLBACK_MODEL=openai/gpt-oss-20b
LLM_FALLBACK_API_KEY=<groq key>

STORAGE_PROVIDER=s3
S3_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
S3_BUCKET=<bucket>
S3_ACCESS_KEY=<r2 access key id>
S3_SECRET_KEY=<r2 secret>
S3_REGION=auto
S3_ADDRESSING_STYLE=path
S3_PUBLIC_URL=https://files.omniscient.co.ke

EMBEDDING_ENABLED=true
RAG_ENABLED=true
ACME_EMAIL=<you@omniscient.co.ke>
```

`SECRET_KEY` and the database password are not recoverable from anywhere
else. Store them in a password manager **now**, not later — losing the
VM means losing `.env`, and nothing else on earth holds those values.

### 5.2 Start and verify

```bash
cd /opt/omniscient
sudo -u omniscient docker compose up -d
sudo -u omniscient docker compose ps        # all four should be healthy
docker compose exec backend curl -fsS http://localhost:8000/api/health
```

Health should report `llm_provider: deepseek`,
`llm_fallback_provider: groq`, `storage_provider: s3`, and
`rag_enabled: true`.

### 5.3 First data

The database starts **empty** — production does not seed demo data.

```bash
# Create the first admin (register in the UI first)
docker compose exec backend python -m app.scripts_entry promote-admin you@student.dekut.ac.ke
```

Then upload past papers through the admin UI. Each upload goes to R2 and
lands in the index queue; build the index with:

```bash
docker compose exec backend python -m app.scripts_entry reindex-past-papers
```

---

## Phase 6 — Go live

```bash
curl -fsS https://omniscient.co.ke/api/health
```

If TLS works, DNS and the firewall are both correct. Then, to hand future
deploys to CI/CD:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

The first deployment is manual (Phase 5) because the workflow needs
credentials that do not exist yet. After this, every release is a tag.

---

## Blockers to clear first

- [ ] **`omniscient.co.ke` does not resolve.** Nothing works until it does.
- [ ] **Ports 80/443 are closed.** Currently only 22 is open.
- [ ] **The arm64 CI job has never run.** It is the only advance warning
      that the ONNX runtime works on Ampere.
- [ ] **Nothing is committed.** There is no `.github/` on the remote.
- [ ] **The deploy key is not installed** on the VM.
- [ ] **Complaint attachments have no access control** unless you pick
      option 2 or 3 in 1.4.
