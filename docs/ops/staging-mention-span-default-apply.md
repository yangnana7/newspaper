# Staging: mention.span DEFAULT apply

## TL;DR
所有者 `newsp` または `postgres` で以下を実行してから検証。

```bash
sudo -u postgres psql newshub -c \
  "ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);"

psql "$DATABASE_URL" -c "\\d mention" | grep -E 'span|DEFAULT'

psql "$DATABASE_URL" -At -c "SELECT column_default FROM information_schema.columns \
 WHERE table_schema='public' AND table_name='mention' AND column_name='span';"
```

## Notes
- 所有者でないユーザー（例: `yang_server`）では `ALTER TABLE` は不可。所有者は `newsp`。
- 出典: staging実行ログの検証結果（docs/daily/2025-08-27-staging-mention-span-default-log.md）。

