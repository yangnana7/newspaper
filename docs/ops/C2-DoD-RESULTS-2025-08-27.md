# C2 DoD — Results & Verification (2025-08-27)

- CI green: pending on remote run. Workflow updated to upload full log + head on failure.
- Local pytest (DB skipped): PASS — `26 passed, 5 skipped`.
- Staging DB `mention.span` DEFAULT: PASS — user verified `int4range(0,0)` via information_schema.
- Timers (staging): ACTION — enable and observe counters; sample units added in `docs/ops/systemd-timers-sample.md`.
- Near-duplicate config tests: PASS — `tests/test_near_duplicate_config.py` added and passing.
- MCP-First UI policy: PASS — `/` returns 404 by default; `docs/UI_MANUAL.md` includes curl procedures.
- Release: ACTION — tag `v0.**` and update CHANGELOG when CI is green.
- Migration duplicates: NOTE — documented in `docs/ops/migrations-note-2025-08-27.md` for post-production consolidation.

## Commands (reference)

### Full test suite with local Postgres
```bash
# If Postgres runs as system service and DB exists
export APP_BIND_HOST=127.0.0.1
export APP_BIND_PORT=3011
export EMBEDDING_SPACE=e5-multilingual
export DATABASE_URL=postgresql://127.0.0.1:5432/newshub

# Init extensions/schema (owner may require sudo -u postgres)
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;" || \
  sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" || \
  sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql "$DATABASE_URL" -f db/schema_v2.sql || sudo -u postgres psql -d newshub -f db/schema_v2.sql
psql "$DATABASE_URL" -f db/indexes_core.sql || sudo -u postgres psql -d newshub -f db/indexes_core.sql
for f in db/migrations/*.sql; do psql "$DATABASE_URL" -f "$f" || sudo -u postgres psql -d newshub -f "$f"; done

pytest -q
```

### Staging: apply `mention.span` DEFAULT
```bash
sudo -u postgres psql newshub -c "ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);"
psql "$DATABASE_URL" -c "\\d mention" | grep -E 'span|DEFAULT'
psql "$DATABASE_URL" -At -c "SELECT column_default FROM information_schema.columns WHERE table_schema='public' AND table_name='mention' AND column_name='span';"
```

### Timers enable + metrics check
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now newshub-linking.timer newshub-events.timer
systemctl list-timers | grep newshub
curl -s http://127.0.0.1:3011/metrics | grep -E 'entities_linked_total|events_with_participants_total'
```

