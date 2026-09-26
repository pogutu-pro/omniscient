#!/usr/bin/env bash
#
# One-time bootstrap for a fresh Oracle Compute instance.
#
# Safe to re-run: every step checks whether it is already done. That
# matters because a bootstrap that half-succeeded and cannot be resumed
# is a bad way to find out that a package manager was briefly unhappy.
#
#   ssh -i ssh-key-2026-09-26.key ubuntu@84.12.101.132 'bash -s' < infra/deploy/bootstrap.sh
#
# What it does:
#   1. installs Docker Engine + the Compose plugin, if missing
#   2. installs the packages the app needs to read PDFs and healthcheck
#   3. creates /opt/omniscient and clones the repo
#   4. leaves .env for you to fill in — it will NOT invent secrets
#
# It deliberately does NOT start the stack. Starting it without real
# credentials produces a container that crash-loops and a first
# migration failure, which is a confusing way to learn what .env needs.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/omniscient}"
REPO_URL="${REPO_URL:-https://github.com/pogutu-pro/omniscient.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
DEPLOY_USER="${DEPLOY_USER:-omniscient}"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mFAILED:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Run as root (sudo bash ...), or as a user with sudo."

# --- 1. Docker ------------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  log "Docker and the Compose plugin are already installed."
  docker --version
  docker compose version
else
  log "Installing Docker Engine and the Compose plugin"
  export DEBIAN_FRONTEND=noninteractive

  # Oracle Linux and the Ubuntu images differ here, and the official
  # Docker apt repo is the only source that has the Compose *plugin*
  # (the `docker-compose` v1 binary is not the same thing and does not
  # support the `--wait` flag the deploy script relies on).
  if command -v dnf >/dev/null 2>&1; then
    dnf -y install dnf-plugins-core
    dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
      https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  else
    fail "Neither dnf nor apt-get found. Install Docker manually, then re-run this script."
  fi

  systemctl enable --now docker
  log "Docker installed."
fi

# --- 2. Runtime packages --------------------------------------------------
# curl backs the backend healthcheck; these two are what PDF text
# extraction needs when a paper is not a clean text-layer PDF.
log "Installing runtime packages"
if command -v dnf >/dev/null 2>&1; then
  dnf -y install curl file-libs poppler-utils
else
  apt-get update
  apt-get install -y curl file poppler-utils
fi

# The 200 GB Always Free block volume is shared with the Docker root, and
# an unbounded image cache is the most common way to fill it. Log rotation
# is set per-container in the compose file; this caps the daemon's own
# layer cache, which those settings do not cover.
log "Configuring Docker log limits"
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
  systemctl restart docker
else
  warn "/etc/docker/daemon.json already exists; leaving it alone."
fi

# --- 3. Deploy user -------------------------------------------------------
# The app does not need root, and giving the deploy key an unprivileged
# account means a compromised CI runner cannot own the whole VM.
if id "$DEPLOY_USER" >/dev/null 2>&1; then
  log "Deploy user ${DEPLOY_USER} already exists."
else
  log "Creating unprivileged deploy user ${DEPLOY_USER}"
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

# --- 4. Application directory and repo -----------------------------------
if [ -d "$APP_DIR/.git" ]; then
  log "Repository already present at ${APP_DIR}; leaving the working tree alone."
  warn "If you are redeploying, run: git -C ${APP_DIR} pull"
else
  log "Cloning into ${APP_DIR}"
  mkdir -p "$APP_DIR"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
  if [ "$(id -u)" -eq 0 ]; then
    su - "$DEPLOY_USER" -c "git clone --branch ${REPO_BRANCH} ${REPO_URL} ${APP_DIR}"
  else
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
  fi
fi

chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR" 2>/dev/null || true
chmod +x "$APP_DIR"/infra/deploy/*.sh 2>/dev/null || true

# --- 5. Hand off ----------------------------------------------------------
cat <<EOF

$(log "Bootstrap complete. The stack has NOT been started.")

Next steps, on this machine:

  1. Create the environment file. It needs real credentials, so it is
     never generated for you:

       sudo -u ${DEPLOY_USER} cp ${APP_DIR}/.env.example ${APP_DIR}/.env
       sudo -u ${DEPLOY_USER} chmod 600 ${APP_DIR}/.env
       sudo -u ${DEPLOY_USER} nano ${APP_DIR}/.env

     At minimum: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
     SECRET_KEY (openssl rand -hex 32), LLM_PROVIDER=deepseek,
     LLM_API_KEY, LLM_FALLBACK_PROVIDER=groq, LLM_FALLBACK_API_KEY,
     STORAGE_PROVIDER=s3 and the S3_* values for your R2 bucket,
     EMBEDDING_ENABLED=true, RAG_ENABLED=true.

  2. Point DNS at this host. omniscient.co.ke and www must both resolve
     here before Caddy can obtain a certificate.

  3. Open ports 80 and 443 in the VCN security list and any NSG attached
     to the instance. Port 22 for SSH, restricted to your own address.

  4. Start the stack:

       cd ${APP_DIR} && sudo -u ${DEPLOY_USER} docker compose up -d

  5. Confirm it came up:

       docker compose ps
       curl -fsS https://omniscient.co.ke/api/health

EOF
