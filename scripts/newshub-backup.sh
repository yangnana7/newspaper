#!/usr/bin/env bash
set -Eeuo pipefail

# T8: Logical backup for PostgreSQL database 'newshub'
# - Format: pg_dump custom (.dump) with internal compression
# - Low IO/CPU priority via ionice + nice
# - SHA256 sidecar for integrity
# - App/config lightweight archive
# - Retention: 21 days (daily)

ENV_FILE=/etc/default/mcp-news
BACKUP_DIR=/var/backups/newshub
APP_DIR=/home/yang_server/newspaper

# run command with low priority
run_low() { ionice -c3 nice -n 19 "$@"; }

# Load DATABASE_URL from ENV_FILE
if [ ! -f "$ENV_FILE" ]; then
  echo "[ERR] ENV file not found: $ENV_FILE" >&2; exit 1
fi
eval "$(grep -E '^(DATABASE_URL)=' "$ENV_FILE" || true)"
if [ -z "${DATABASE_URL:-}" ]; then
  echo "[ERR] DATABASE_URL not set" >&2; exit 1
fi

ts="$(date +%Y%m%d-%H%M%S)"
db_dump="${BACKUP_DIR}/newshub-${ts}.dump"
sha_file="${db_dump}.sha256"

# Ensure directories exist (permissions should be pre-provisioned by ops)
if [ ! -d "$BACKUP_DIR" ]; then
  echo "[ERR] backup dir not found: $BACKUP_DIR" >&2; exit 1
fi
mkdir -p "${BACKUP_DIR}/app"

# Database dump
run_low pg_dump --dbname="$DATABASE_URL" --format=custom --blobs --compress=9 --file="$db_dump"

# SHA256 sidecar (write relative path for sha256sum -c)
(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$db_dump")" > "$(basename "$sha_file")"
) 

# Config/app lightweight archive (best-effort)
tar czf "${BACKUP_DIR}/app/app-${ts}.tgz" \
  /etc/default/mcp-news \
  /etc/systemd/system/mcp-news.service \
  "$APP_DIR" 2>/dev/null || true

# Retention (21 days)
find "$BACKUP_DIR" -type f -name 'newshub-*.dump' -mtime +21 -delete || true
find "$BACKUP_DIR/app" -type f -name 'app-*.tgz' -mtime +21 -delete || true

echo "[OK] backup done: ${db_dump}"

