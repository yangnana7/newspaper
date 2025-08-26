# Migration: mention.span DEFAULT int4range(0,0)

対象: staging / production の PostgreSQL データベース（DB 名は固定 `newshub`）
目的: `mention.span` に安全な既定値（空レンジ `int4range(0,0)`）を設定し、NOT NULL + PK を常に満たす。

## 前提（MCP-First 固定値）
- `DATABASE_URL=postgresql://127.0.0.1:5432/newshub`
- `APP_BIND_HOST=127.0.0.1` / `APP_BIND_PORT=3011`

## 適用手順（staging）
```bash
# 1) DB到達確認
psql "$DATABASE_URL" -c '\\conninfo'

# 2) スキーマが未適用の場合は適用（冪等）
psql "$DATABASE_URL" -f db/schema_v2.sql
psql "$DATABASE_URL" -f db/indexes_core.sql

# 3) 今回のマイグレーション適用（冪等）
psql "$DATABASE_URL" -f db/migrations/2025-08-27_mention_span_default.sql
```

## 検証
```bash
# カラム定義に DEFAULT が付いたことを確認
psql "$DATABASE_URL" -c "\\\d mention" | grep -E 'span|default'

# もしくは information_schema で確認
psql "$DATABASE_URL" -c "\
  SELECT column_default \
  FROM information_schema.columns \
  WHERE table_schema='public' AND table_name='mention' AND column_name='span';\
"
```
期待値: `int4range(0,0)` が DEFAULT として表示される。

## ロールバック（必要時）
```bash
psql "$DATABASE_URL" -c "ALTER TABLE mention ALTER COLUMN span DROP DEFAULT;"
```

## 備考
- CI では `db/migrations/*.sql` を順次適用するステップが入っています（GitHub Actions 確認）。
- `scripts/ingest_entities.py` は空レンジを前提に安全挿入します（将来、オフセット更新で精密化）。
