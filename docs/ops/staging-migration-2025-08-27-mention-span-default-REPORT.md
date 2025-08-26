# Staging Migration Report — mention.span DEFAULT int4range(0,0)

- Target: PostgreSQL `newshub` (staging)
- Scope: Apply DEFAULT `int4range(0,0)` to `mention.span` and verify

## What’s in repo
- Migration file: `db/migrations/2025-08-27_mention_span_default.sql`
  - Contents: `ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);`
- Note: `db/migrations/2025-08-26_mention_span_default.sql` also exists with the same statement (idempotent).

## Commands (staging)
Use these exact commands (correct quoting for psql meta-commands):

```bash
# 0) Ensure DATABASE_URL is set or use a full DSN
# export DATABASE_URL=postgresql://127.0.0.1:5432/newshub

# If password is required, either:
#  - set PGPASSWORD and include user in DSN, e.g.
#    PGPASSWORD='***' psql 'postgresql://yang_server@127.0.0.1:5432/newshub' -c '\conninfo'
#  - or use local peer auth as postgres user

# 1) DB reachability
psql "$DATABASE_URL" -c '\conninfo'

# 2) (Optional, idempotent) Ensure base schema + indexes are present
psql "$DATABASE_URL" -f db/schema_v2.sql
psql "$DATABASE_URL" -f db/indexes_core.sql

# 3) Apply the migration (idempotent)
psql "$DATABASE_URL" -f db/migrations/2025-08-27_mention_span_default.sql

# 4) Verify DEFAULT is in place (two options)
psql "$DATABASE_URL" -c '\d mention' | grep -E 'span|DEFAULT'
psql "$DATABASE_URL" -c "\
  SELECT column_default \
  FROM information_schema.columns \
  WHERE table_schema='public' AND table_name='mention' AND column_name='span';\
"
```

Expected: `int4range(0,0)` appears as the DEFAULT for `mention.span`.

## Notes
- The previous error “invalid command \” was due to over-escaping. Prefer single quotes around psql meta-commands, e.g. `-c '\\d mention'` is unnecessary; `-c '\d mention'` is correct, and `-c '\conninfo'` works as shown above.
- Re-applying the migration is safe; `SET DEFAULT` is idempotent for the same value.

## Status
- Repository prepared with the correct migration file.
- Staging application/verification pending on DB credentials/connection.

