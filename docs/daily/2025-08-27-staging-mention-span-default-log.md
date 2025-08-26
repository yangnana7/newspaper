# Staging Run Log — mention.span DEFAULT int4range(0,0)

- When: 2025-08-27
- Target DB: `newshub` on `127.0.0.1:5432`
- User: `yang_server`

## Steps and results

1) Connection check
```
psql "$DSN" -c '\\conninfo'
=> OK: connected as user "yang_server" to database "newshub" (host 127.0.0.1, port 5432)
```

2) Base schema/index (skipped due to privileges)
```
Attempted: psql -f db/schema_v2.sql
Result: ERROR: permission denied for schema public (user lacks CREATE)
Action: Skipped schema/index steps (not required for this migration if schema already present)
```

3) Apply migration (idempotent)
```
File: db/migrations/2025-08-27_mention_span_default.sql
Stmt: ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);
Result: No error surfaced, but verification shows DEFAULT not set (see below). Likely requires table owner privileges.
```

4) Verification
```
psql -c '\\d mention' | grep -Ei 'span|default'
=> span int4range | not null | (Default is empty)

psql -At -c "SELECT column_default FROM information_schema.columns \
  WHERE table_schema='public' AND table_name='mention' AND column_name='span';"
=> (empty)
```

5) Table owner
```
SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename='mention';
=> newsp
```

## Conclusion
- Migration NOT applied due to insufficient privileges. User `yang_server` is not the owner of `public.mention`.
- `ALTER TABLE` requires the table owner or a superuser.

## Next actions (choose one)
- Connect as the owner `newsp` (or superuser `postgres`) and run:
```
psql 'postgresql://<OWNER>@127.0.0.1:5432/newshub' -c \
  "ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);"
```
- Or run locally on the server with peer auth:
```
sudo -u postgres psql newshub -c \
  "ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);"
```

## Post-apply verification
```
psql "$DSN" -c '\\d mention' | grep -Ei 'span|default'
psql "$DSN" -At -c "SELECT column_default FROM information_schema.columns \
  WHERE table_schema='public' AND table_name='mention' AND column_name='span';"
# Expect: int4range(0,0)
```

