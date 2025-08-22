# Ubuntu 検証手順（AIエージェント向け）

本手順は docs/マニュアル.md の固定条件に準拠し、現在のソース（web.app:app 提供）での検証観点を明示します。HTTPアプリは `web.app:app` を使用します（MCPツールは `mcp_news.server`）。

**固定条件（遵守）**
- DB: `newshub`
- バインド先: `127.0.0.1:3011`（外部公開はNginxで終端。アプリはローカル待受）
- スキーマ: 既存 `doc/chunk/chunk_vec/entity/event/hint` は変更禁止（追加DDLはIF NOT EXISTS/DO $$ で冪等）
- ベクトル: `vector(768)`、距離は cosine のみ（`<=>` / `vector_cosine_ops`）
- タイムゾーン: DB保存=UTC、表示=JST

## 1) 前提パッケージ

```
sudo apt update && sudo apt install -y \
  python3.11 python3.11-venv python3-pip \
  postgresql postgresql-contrib postgresql-16-pgvector
```

## 2) 仮想環境と依存

```
python3 -m venv /opt/mcp-news/.venv
source /opt/mcp-news/.venv/bin/activate
pip install -U pip
pip install -r requirements.txt
export PYTHONPATH=.
```

推奨の EnvironmentFile（systemd 用）: `/etc/default/mcp-news`

```
DATABASE_URL=postgresql://127.0.0.1:5432/newshub
APP_BIND_HOST=127.0.0.1
APP_BIND_PORT=3011
EMBED_SPACE=bge-m3
EMBEDDING_SPACE=bge-m3
ENABLE_SERVER_EMBEDDING=0
LOG_LEVEL=info
```

## 3) DB 初期化と拡張

```
sudo -u postgres psql <<'SQL'
CREATE DATABASE newshub;
\c newshub
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL
```

## 4) スキーマと運用インデックス適用

```
psql "$DATABASE_URL" -f db/schema_v2.sql
psql "$DATABASE_URL" -f db/indexes_core.sql
```

確認:

```
psql "$DATABASE_URL" -c "SELECT to_regclass('doc'), to_regclass('chunk'), to_regclass('chunk_vec');"
psql "$DATABASE_URL" -c "SELECT indexname FROM pg_indexes WHERE tablename IN ('doc','hint','chunk_vec') ORDER BY 1;"
```

## 5) 最小データ投入

```
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "INSERT INTO doc (source,url_canon,title_raw,published_at,first_seen_at,raw) \
    VALUES ('test://local','https://example.com/1','Hello World', now() at time zone 'UTC', now() at time zone 'UTC', '{}'::jsonb) \
    ON CONFLICT (url_canon) DO NOTHING;"

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "WITH d AS (SELECT doc_id FROM doc WHERE url_canon='https://example.com/1') \
    INSERT INTO chunk (doc_id,part_ix,text_raw,lang,created_at) \
    SELECT d.doc_id,0,'Hello world body for semantic search','en', now() at time zone 'UTC' \
    FROM d ON CONFLICT DO NOTHING;"

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "WITH d AS (SELECT doc_id FROM doc WHERE url_canon='https://example.com/1') \
    INSERT INTO hint (doc_id,key,val,conf) \
    SELECT d.doc_id,'genre_hint','news',0.8 FROM d \
    ON CONFLICT (doc_id,key) DO UPDATE SET val = EXCLUDED.val, conf = EXCLUDED.conf;"
```

## 6) 埋め込み（任意・推奨）

```
python scripts/embed_chunks.py --space bge-m3 --batch 64
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM chunk_vec WHERE embedding_space='bge-m3';"
```

## 7) HTTP アプリ起動（127.0.0.1:3011）

```
mkdir -p web/static
uvicorn web.app:app --host 127.0.0.1 --port 3011
```

systemd（任意）: `/etc/systemd/system/newshub-api@.service`

```
[Unit]
Description=Newshub API (FastAPI) for %i
After=network-online.target
Wants=network-online.target

[Service]
User=%i
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/uvicorn web.app:app --host ${APP_BIND_HOST} --port ${APP_BIND_PORT}
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl daemon-reload
sudo systemctl enable --now newshub-api@${USER}.service
journalctl -u newshub-api@${USER}.service -n 200 --no-pager
```

## 8) API 検証（全て 127.0.0.1:3011 宛）

```
curl "http://127.0.0.1:3011/api/latest?limit=5"
curl "http://127.0.0.1:3011/api/search?q=Hello&limit=5&offset=0"
curl "http://127.0.0.1:3011/api/search_sem?limit=3"   # qなし → 新着フォールバック
```

埋め込み指定（q=JSON 数値配列）:

```
VEC=$(python - <<'PY'
import json; from sentence_transformers import SentenceTransformer
m=SentenceTransformer('intfloat/multilingual-e5-base')
print(json.dumps(m.encode(['Hello world body for semantic search'], normalize_embeddings=True)[0].tolist()))
PY
)
curl --get -s --data-urlencode "q=$VEC" \
  "http://127.0.0.1:3011/api/search_sem?limit=5&offset=0&space=bge-m3"
```

期待:
- `api/latest`: サンプル記事が配列で返る
- `api/search`: ILIKE でヒット
- `api/search_sem`: qなしは新着順、qありは `chunk_vec` が存在すれば類似順（存在しない場合は空配列）

## 9) レポート収集（提出物）

- `schema_v2.sql` と `indexes_core.sql` 適用ログ（エラーなし）
- `pg_indexes` 一覧（doc/hint/chunk_vec）
- `/api/latest` `/api/search` `/api/search_sem` 各レスポンス例（小さなJSONでOK）
- `embed_chunks.py` 実行ログ（挿入件数・pending 0）
- 任意: `EXPLAIN ANALYZE SELECT 1 FROM doc WHERE title_raw ILIKE '%Hello%' LIMIT 10;`

## 10) トラブルシュート

- `CREATE EXTENSION` はDB内で実行（権限要）。`vector`/`pg_trgm` の導入を確認
- `web/static` 不在でも起動可能だが、作成を推奨（ログ/配信用途）
- 変数ロック: `DATABASE_URL` は必ず `/newshub` を含み、`APP_BIND_HOST/PORT=127.0.0.1:3011`
- モデルDLが必要な環境では `SentenceTransformer` 利用時にネットワーク要件に注意

