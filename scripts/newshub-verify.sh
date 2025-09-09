#!/usr/bin/env bash
set -Eeuo pipefail

# T8: Weekly restore verification for 'newshub'
# - Restores latest dump into temporary DB 'newshub_verify'
# - Runs basic presence/count checks
# - Confirms vector_cosine_ops index (if present)

ENV_FILE=/etc/default/mcp-news
BACKUP_DIR=/var/backups/newshub
VERIFY_DB=newshub_verify

if [ ! -f "$ENV_FILE" ]; then
  echo "[ERR] ENV file not found: $ENV_FILE" >&2; exit 1
fi

eval "$(grep -E '^(DATABASE_URL)=' "$ENV_FILE" || true)"
if [ -z "${DATABASE_URL:-}" ]; then
  echo "[ERR] DATABASE_URL not set" >&2; exit 1
fi

# Find latest dump
latest="$(ls -1t ${BACKUP_DIR}/newshub-*.dump 2>/dev/null | head -n1 || true)"
if [ -z "$latest" ]; then
  echo "[ERR] no dumps found in $BACKUP_DIR" >&2; exit 1
fi

echo "[INFO] latest dump: $latest"

# Create temp DB, restore, check, drop
psql -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS ${VERIFY_DB};"
psql -v ON_ERROR_STOP=1 -d postgres -c "CREATE DATABASE ${VERIFY_DB};"

pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname="${VERIFY_DB}" "$latest"

echo "[INFO] row counts (doc/chunk/chunk_vec)"
psql -d "${VERIFY_DB}" -Atc "
SELECT 'doc', count(*) FROM doc
UNION ALL
SELECT 'chunk', count(*) FROM chunk
UNION ALL
SELECT 'chunk_vec', count(*) FROM chunk_vec;" | sed 's/\t/: /g'

echo "[INFO] vector_cosine_ops indexes on chunk_vec (if any)"
psql -d "${VERIFY_DB}" -Atc "
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename='chunk_vec' AND indexdef ILIKE '%vector_cosine_ops%';"

psql -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS ${VERIFY_DB};"
echo "[OK] verify done for ${latest}"
