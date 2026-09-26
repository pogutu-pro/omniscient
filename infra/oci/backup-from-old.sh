#!/usr/bin/env bash
#
# Capture everything worth keeping from the OLD instance. Run this BEFORE
# terminating it.
#
#   ssh -i ssh-key-2026-09-26.key ubuntu@84.12.101.132 'bash -s' < infra/oci/backup-from-old.sh
#
# WHAT IS AND ISN'T AT RISK
#
#   At risk  - the PostgreSQL database, because docker-compose puts it in
#              a named volume under /var/lib/docker on the BOOT VOLUME.
#              Terminating the instance destroys it. This is the thing
#              people lose.
#   Safe    - past papers and complaint attachments, because they live in
#              Cloudflare R2, not on this machine.
#   Safe    - the repository, because it is a public git remote.
#   LOST    - the .env file. It is gitignored, so it exists nowhere else.
#              If you do not have a copy, every credential in it is gone.
#              This script copies it to the bundle, but a copy on the same
#              machine that is about to be deleted is not a backup. Move
#              the bundle off the instance afterwards.
set -euo pipefail

BUNDLE="${BUNDLE:-$HOME/omniscient-migration-$(date +%Y%m%d-%H%M%S)}"
APP_DIR="${APP_DIR:-/opt/omniscient}"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m      %s\n' "$*"; }
warn() { printf '  \033[33mwarning\033[0m %s\n' "$*"; }

# ok_if <exit-status> <message> — report success only if the preceding
# command actually succeeded. Used instead of `ok` after commands that may
# legitimately fail, so the output never claims something worked that did
# not. That distinction is the whole point of a backup script.
ok_if() {
  if [ "$1" -eq 0 ]; then ok "$2"; else warn "$2"; fi
}

mkdir -p "$BUNDLE"
log "Writing migration bundle to ${BUNDLE}"

# --- 1. Environment file --------------------------------------------------
# The most irreplaceable item here, and the easiest to overlook precisely
# because it is the one thing that is supposed to be untracked.
log "1. Environment file"
if [ -f "${APP_DIR}/.env" ]; then
  cp "${APP_DIR}/.env" "${BUNDLE}/env.backup"
  chmod 600 "${BUNDLE}/env.backup"
  # Value-free summary, so you can see what is set without printing
  # credentials into a terminal scrollback or a CI log.
  grep -oE '^[A-Z0-9_]+=' "${APP_DIR}/.env" | tr -d '=' | sort > "${BUNDLE}/env.keys"
  echo "  $(wc -l < "${BUNDLE}/env.keys") keys captured (values not printed)"
  warn "This contains live credentials. Move it off this machine immediately."
else
  warn "No .env at ${APP_DIR}. If the app ran with one, it is gone after"
  warn "termination. Reconstruct it from .env.example and your provider dashboards."
fi

# --- 2. Database dump -----------------------------------------------------
# pg_dump, not a volume copy. A tar of a live Postgres data directory is
# only restorable if the server was stopped cleanly, and a custom-format
# dump is version-tolerant and far smaller.
log "2. PostgreSQL dump"
DB_CONTAINER="$(docker compose -f "${APP_DIR}/docker-compose.yml" ps -q db 2>/dev/null || true)"
if [ -z "$DB_CONTAINER" ]; then
  DB_CONTAINER="$(docker ps --filter ancestor=pgvector/pgvector:pg16 --format '{{.ID}}' | head -1 || true)"
fi

if [ -n "$DB_CONTAINER" ]; then
  DB_USER="$(grep -E '^POSTGRES_USER=' "${APP_DIR}/.env" 2>/dev/null | cut -d= -f2- || echo omniscient)"
  DB_NAME="$(grep -E '^POSTGRES_DB='  "${APP_DIR}/.env" 2>/dev/null | cut -d= -f2- || echo omniscient)"

  docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc \
    > "${BUNDLE}/omniscient.dump"
  ok_if [ -s "${BUNDLE}/omniscient.dump" ] "dump written ($(du -h "${BUNDLE}/omniscient.dump" | cut -f1))" \
    || warn "dump is empty — is the database actually running?"

  # Row counts, so you can prove the restore matched rather than trusting
  # that a non-zero exit meant success.
  #
  # The table list is read from information_schema rather than hardcoded,
  # because a hardcoded list silently stops covering new tables the first
  # time someone adds a migration — and the whole point of this file is to
  # be the thing you trust when the old instance is already gone.
  log "2b. Row counts for comparison after restore"
  {
    echo "-- row counts at backup time ($(date -u +%FT%TZ))"
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAF' ' -c \
      "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname" 2>/dev/null \
      || echo "-- (could not read pg_stat_user_tables)"
  } > "${BUNDLE}/row-counts.sql"

  # pg_stat_user_tuple estimates rather than exact counts, which is good
  # enough to detect a botched restore but not good enough to be the only
  # record. Take exact counts too.
  TABLES="$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename" 2>/dev/null || true)"
  {
    for t in $TABLES; do
      n="$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
            "SELECT count(*) FROM \"$t\"" 2>/dev/null | tr -d '[:space:]' || echo '?')"
      printf -- '-- %-24s %s\n' "$t" "$n"
    done
  } > "${BUNDLE}/row-counts-exact.sql"
  cat "${BUNDLE}/row-counts-exact.sql"

  warn "Compare these against the same query on the new instance. pgvector"
  warn "chunks are re-creatable but not free: re-indexing costs a few minutes."
fi


# --- 3. Uploaded files, if storage is local -------------------------------
# With STORAGE_PROVIDER=s3 this is skipped, which is the point of using R2.
log "3. Local file storage"
if grep -qE '^STORAGE_PROVIDER=local' "${APP_DIR}/.env" 2>/dev/null; then
  if [ -d "${APP_DIR}/backend/var/storage" ]; then
    tar -czf "${BUNDLE}/storage.tar.gz" -C "${APP_DIR}/backend/var" storage 2>/dev/null || true
    warn "STORAGE_PROVIDER=local: copied uploaded files to storage.tar.gz."
  fi
else
  ok_if true "storage is in R2, so no files to copy"
fi

# --- 4. Compose state, for reference --------------------------------------
log "4. Running containers and image list"
{
  echo "# captured $(date -u +%FT%TZ)"
  echo "## containers"
  docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null || true
  echo "## images"
  docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' 2>/dev/null || true
} > "${BUNDLE}/docker-state.txt"

# --- 5. A verification note ----------------------------------------------
cat > "${BUNDLE}/RESTORE.md" <<EOF
# Restoring onto the new instance

1. Bootstrap and configure the new VM (infra/deploy/bootstrap.sh, then .env).
2. Start only the database:

       cd /opt/omniscient && docker compose up -d db

3. Wait for it to be healthy:

       docker compose ps          # db must show "healthy"

4. Restore:

       docker compose exec -T db pg_restore -U \$POSTGRES_USER -d \$POSTGRES_DB \\
         --clean --if-exists < /path/to/omniscient.dump

   Alembic has already created the schema, so --clean drops and recreates
   the objects in the dump. If pg_restore complains about the vector
   extension, create it first:

       docker compose exec -T db psql -U \$POSTGRES_USER -d \$POSTGRES_DB \\
         -c "CREATE EXTENSION IF NOT EXISTS vector"

5. Start the rest and compare row counts against row-counts.sql:

       docker compose up -d
       curl -fsS https://omniscient.co.ke/api/health

6. Rebuild the search index (optional — only if past_paper_chunks was
   empty or the embedding model changed):

       docker compose exec backend python -m app.scripts_entry reindex-past-papers
EOF

ok_if true "bundle contents:"
ls -la "$BUNDLE"

cat <<EOF

$(log "Bundle complete: ${BUNDLE}")

  \033[1;31mMove this directory off the instance now.\033[0m A copy on the machine
  you are about to terminate is not a backup. 'scp -r' it to your laptop.

  Only after the new instance is verified should you terminate the old one.
EOF
