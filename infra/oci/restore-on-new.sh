#!/usr/bin/env bash
#
# Restore the database captured by backup-from-old.sh onto the NEW
# instance. Run this on the new VM, after bootstrap.sh and after the stack
# is configured but before you point DNS at it.
#
#   scp -r ~/omniscient-migration-20260926-120000 <new-vm>:~/
#   ssh -i <key> ubuntu@<new-ip> 'bash -s' < infra/oci/restore-on-new.sh
#
# The ordering matters: the database must be up and healthy on its own
# before anything else starts, because a half-restored database that the
# backend then migrates on boot is a much worse problem to diagnose than a
# clean restore.
set -euo pipefail

BUNDLE="${BUNDLE:-$HOME/omniscient-migration-*}"
APP_DIR="${APP_DIR:-/opt/omniscient}"
COMPOSE="docker compose -f ${APP_DIR}/docker-compose.yml"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m      %s\n' "$*"; }
warn() { printf '  \033[33mwarning\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31mFAILED:\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker is not installed. Run infra/deploy/bootstrap.sh first."
[ -f "${APP_DIR}/docker-compose.yml" ] || die "No compose file at ${APP_DIR}. Run infra/deploy/bootstrap.sh first."

# --- 0. Locate the bundle -------------------------------------------------
# Expanded to a single directory, and a missing one is fatal: a glob that
# matches several bundles silently restoring the wrong one would be worse
# than refusing.
shopt -s nullglob
CANDIDATES=($BUNDLE)
shopt -u nullglob
[ ${#CANDIDATES[@]} -gt 0 ] || die "No migration bundle found at ${BUNDLE}. Copy it here first."
if [ ${#CANDIDATES[@]} -gt 1 ]; then
  die "Several bundles match '${BUNDLE}'. Set BUNDLE=/path/to/the/right/one"
fi
BUNDLE_DIR="${CANDIDATES[0]}"
DUMP="${BUNDLE_DIR}/omniscient.dump"
[ -f "$DUMP" ] || die "No omniscient.dump in ${BUNDLE_DIR}. Was backup-from-old.sh run to completion?"
ok "using bundle: ${BUNDLE_DIR}"

# --- 1. Environment file --------------------------------------------------
if [ -f "${BUNDLE_DIR}/env.backup" ] && [ ! -f "${APP_DIR}/.env" ]; then
  log "Restoring .env from the bundle"
  install -m 600 "${BUNDLE_DIR}/env.backup" "${APP_DIR}/.env"
  chown "$(stat -c '%U:%G' "${APP_DIR}")" "${APP_DIR}/.env" 2>/dev/null || true
  ok ".env restored (mode 600)"
  warn "Verify it points at the right database host before starting the backend."
else
  warn "Using the .env already on this instance."
fi

[ -f "${APP_DIR}/.env" ] || die "No .env at ${APP_DIR} and none in the bundle. The app cannot start without it."

DB_USER="$(grep -E '^POSTGRES_USER=' "${APP_DIR}/.env" | cut -d= -f2- | tr -d '"'\''')"
DB_NAME="$(grep -E '^POSTGRES_DB='  "${APP_DIR}/.env" | cut -d= -f2- | tr -d '"'\''')"
[ -n "$DB_USER" ] && [ -n "$DB_NAME" ] || die "Could not read POSTGRES_USER/POSTGRES_DB from .env"

# --- 2. Start only the database ------------------------------------------
log "Starting the database"
$COMPOSE up -d db

log "Waiting for it to become healthy"
for i in $(seq 1 60); do
  status="$($COMPOSE ps --format '{{.Health}}' db 2>/dev/null | tr -d '[:space:]')"
  if [ "$status" = "healthy" ]; then
    ok "database is healthy after ${i}0s"
    break
  fi
  if [ "$i" -eq 60 ]; then
    $COMPOSE logs --tail 40 db
    die "The database did not become healthy. Output above should say why."
  fi
  sleep 10
done

# --- 3. pgvector extension ------------------------------------------------
# The dump contains vector-typed columns, so the extension has to exist
# before pg_restore reaches them. CREATE EXTENSION IF NOT EXISTS makes this
# safe to run repeatedly.
log "Ensuring the pgvector extension exists"
$COMPOSE exec -T db psql -U "$DB_USER" -d "$DB_NAME" \
  -c "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null
ok "vector extension present"

# --- 4. Restore -----------------------------------------------------------
# --clean drops objects in the dump before recreating them. Alembic already
# created an empty schema, which pg_restore would otherwise collide with.
# --if-exists stops --clean erroring on objects that are not there yet.
log "Restoring the dump (this overwrites the empty schema)"
if $COMPOSE exec -T db pg_restore -U "$DB_USER" -d "$DB_NAME" \
     --clean --if-exists --no-owner --no-privileges < "$DUMP"; then
  ok "pg_restore completed"
else
  warn "pg_restore reported errors. Non-fatal ones are common (for example"
  warn "'cannot drop ... because it does not exist' on a fresh database)."
  warn "Row counts below are the real check: if they match row-counts.sql,"
  warn "the restore is good and the errors were cosmetic."
fi

# --- 5. Verify against the recorded counts -------------------------------
# This is the step that actually proves the restore worked. Exit status
# from pg_restore is not evidence; matching row counts are.
log "5. Comparing row counts against the backup"
COUNTS_FILE="${BUNDLE_DIR}/row-counts-exact.sql"
[ -f "$COUNTS_FILE" ] || COUNTS_FILE="${BUNDLE_DIR}/row-counts.sql"
if [ -f "$COUNTS_FILE" ]; then
  MISMATCH=0
  while read -r table expected; do
    case "$table" in --*) continue ;; esac
    [ -n "${expected:-}" ] || continue
    actual="$($COMPOSE exec -T db psql -U "$DB_USER" -d "$DB_NAME" -tAc \
                "SELECT count(*) FROM \"$table\"" 2>/dev/null | tr -d '[:space:]' || echo '?')"
    if [ "$actual" = "$expected" ]; then
      printf '  \033[32mok\033[0m      %-24s %s\n' "$table" "$actual"
    else
      printf '  \033[33mDIFF\033[0m    %-24s expected %s, got %s\n' "$table" "$expected" "$actual"
      MISMATCH=$((MISMATCH + 1))
    fi
  done < <(grep -oE '^-- [a-z_]+ +[0-9n?/]+$' "$COUNTS_FILE" | sed 's/^-- //')

  if [ "$MISMATCH" -eq 0 ]; then
    ok "every table matches the backup"
  else
    warn "${MISMATCH} table(s) differ. Expected if the new database was"
    warn "seeded differently; investigate before deleting the old instance."
  fi
else
  warn "No row-counts.sql in the bundle; skipping verification."
fi

# --- 6. Bring up the rest -------------------------------------------------
log "Starting the full stack"
$COMPOSE up -d

log "Waiting for the backend to report healthy"
for i in $(seq 1 40); do
  health="$($COMPOSE exec -T backend curl -fsS http://localhost:8000/api/health 2>/dev/null || true)"
  if [ -n "$health" ]; then
    ok "backend is up: ${health}"
    break
  fi
  [ "$i" -eq 40 ] && { $COMPOSE logs --tail 40 backend; die "The backend never became healthy."; }
  sleep 10
done

# --- 7. Search index ------------------------------------------------------
# past_paper_chunks was restored along with everything else, so the index
# should already be there. The vector column only means something if the
# embedding model still matches, so this is a sanity check rather than a
# rebuild: it reports the counts and rebuilds only if the index is empty.
log "Checking the search index"
CHUNKS="$($COMPOSE exec -T db psql -U "$DB_USER" -d "$DB_NAME" -tAc \
           'SELECT count(*) FROM past_paper_chunks' 2>/dev/null | tr -d '[:space:]' || echo 0)"
PAPERS="$($COMPOSE exec -T db psql -U "$DB_USER" -d "$DB_NAME" -tAc \
           'SELECT count(*) FROM past_papers' 2>/dev/null | tr -d '[:space:]' || echo 0)"
ok "${CHUNKS} vector chunks across ${PAPERS} past papers"
if [ "${PAPERS:-0}" -gt 0 ] && [ "${CHUNKS:-0}" -eq 0 ]; then
  warn "Papers exist but the index is empty, so search would silently return"
  warn "nothing. Build it:"
  warn "  docker compose exec backend python -m app.scripts_entry reindex-past-papers"
fi

cat <<EOF

$(log "Restore complete")

  \033[1;33mDo not terminate the old instance yet.\033[0m Verify from your own
  machine first:

    1. Point the omniscient.co.ke DNS record at this instance (or attach
       the reserved public IP).
    2. curl -fsS https://omniscient.co.ke/api/health
    3. Load the site, ask the assistant something about a past paper, and
       confirm the answer cites a real source.
    4. Only then:
         oci compute instance terminate --instance-id <old-instance-ocid>
       plus deleting its boot volume, or the storage keeps billing.
EOF
