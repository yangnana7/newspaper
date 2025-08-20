#!/usr/bin/env bash
set -euo pipefail

DB_NAME=${DB_NAME:-newshub}
DB_USER=${DB_USER:-}
DB_PASS=${DB_PASS:-}

echo "[+] Creating database: ${DB_NAME}"
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${DB_NAME}\";" || echo "[i] Database may already exist"

echo "[+] Enabling extensions (pgvector; pgroonga optional)"
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;"
# sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS pgroonga;"  # optional

echo "[+] Applying schema (db/schema_v2.sql)"
psql "postgresql://localhost/${DB_NAME}" -v ON_ERROR_STOP=1 -f db/schema_v2.sql

echo "[✓] DB setup completed"

