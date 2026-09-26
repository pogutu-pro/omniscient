#!/usr/bin/env bash
#
# Roll a new image pair out to the production VM. Executed on the VM by the
# `deploy` GitHub Actions job over SSH; see .github/workflows/deploy.yml.
#
# Inputs (passed as environment variables by the workflow):
#   IMAGE_TAG       - tag to deploy, e.g. v1.4.0 or a commit SHA
#   BACKEND_IMAGE   - fully qualified backend image reference
#   FRONTEND_IMAGE  - fully qualified frontend image reference
#
# Credentials are never passed in. The `.env` file on the VM holds
# POSTGRES_PASSWORD, SECRET_KEY, the DeepSeek and Groq keys, and the R2
# keys; it is created once by an operator and never read, written, or
# logged by this script.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/omniscient}"
REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_OWNER="${IMAGE_OWNER:-pogutu-pro}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31mFAILED:\033[0m %s\n' "$*" >&2; exit 1; }

cd "$APP_DIR"

# --- Preflight -----------------------------------------------------------
# Everything that can be checked without touching the running site is
# checked first, so a typo fails in seconds instead of after a restart.
[ -f "$COMPOSE_FILE" ] || fail "$COMPOSE_FILE not found in $APP_DIR"
[ -f .env ] || fail ".env is missing in $APP_DIR. It must exist and be mode 600; see docs/DEPLOYMENT.md."

command -v docker >/dev/null 2>&1 || fail "docker is not installed or not on PATH"
docker compose version >/dev/null 2>&1 || fail "the docker compose plugin is not available"

# Required keys, checked for presence only — values are never echoed.
# `docker compose` reads .env from this directory on its own, so these
# values are used for interpolation without being extracted into the
# environment here. Shelling out to grep for a password is how a password
# containing "=" or a quote ends up subtly wrong.
for key in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB SECRET_KEY; do
  if ! grep -qE "^${key}=.+" .env; then
    fail "${key} is missing or empty in .env"
  fi
done

export IMAGE_TAG BACKEND_IMAGE FRONTEND_IMAGE

# --- Pull ----------------------------------------------------------------
# Pull first, then restart. Pulling after the old containers are stopped
# turns a slow or failed registry pull into downtime.
log "Pulling images for ${IMAGE_TAG}"
docker compose -f "$COMPOSE_FILE" pull --quiet

# --- Roll out ------------------------------------------------------------
# --wait blocks until every container is healthy or reports failure, so a
# broken image is caught here rather than by a student. The healthcheck
# start periods are long enough to cover migrations and the first model
# load.
log "Applying the new images"
if ! docker compose -f "$COMPOSE_FILE" up -d --remove-orphans --wait --wait-timeout 300; then
  log "Rollout failed. Reverting to the previous images."
  # Read the image the *running* container reports, not what .env says:
  # that is what the site is actually serving, and it is the only thing
  # guaranteed to exist in the registry.
  PREVIOUS_BACKEND="$(docker inspect --format '{{.Config.Image}}' "$(docker compose -f "$COMPOSE_FILE" ps -q backend 2>/dev/null)" 2>/dev/null || true)"
  PREVIOUS_FRONTEND="$(docker inspect --format '{{.Config.Image}}' "$(docker compose -f "$COMPOSE_FILE" ps -q frontend 2>/dev/null)" 2>/dev/null || true)"
  if [ -n "$PREVIOUS_BACKEND" ] && [ -n "$PREVIOUS_FRONTEND" ]; then
    BACKEND_IMAGE="$PREVIOUS_BACKEND" FRONTEND_IMAGE="$PREVIOUS_FRONTEND" \
      docker compose -f "$COMPOSE_FILE" up -d --wait --wait-timeout 300 \
      || fail "Rollback also failed. The site is down and needs manual attention."
    log "Rolled back to ${PREVIOUS_BACKEND}."
  else
    fail "Could not determine the previous image; the site is down and needs manual attention."
  fi
  exit 1
fi

# --- Prune ---------------------------------------------------------------
# Without this, every deploy leaves a full set of images on a 200 GB boot
# volume and the disk fills after a handful of releases.
log "Removing dangling images"
docker image prune -f --filter "until=168h" >/dev/null

# --- Report --------------------------------------------------------------
log "Deployed ${IMAGE_TAG}"
docker compose -f "$COMPOSE_FILE" ps --format 'table {{.Service}}\t{{.Status}}'
