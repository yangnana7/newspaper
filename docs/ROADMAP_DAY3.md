# Day3 Roadmap (Indexes + Semantic Search)

This note summarizes how to apply the additional DB indexes, verify the new semantic search endpoint, and run the minimal HTTP app.

- DB: PostgreSQL 16 with `pgvector` and `pg_trgm`
- Vector: `chunk_vec.emb` uses `vector(768)`; cosine distance only (`<=>` / `vector_cosine_ops`)
- Timezone: store UTC in DB, present JST in API/UI

## 1) Apply schema and operational indexes

```
psql "$DATABASE_URL" -f db/schema_v2.sql
psql "$DATABASE_URL" -f db/indexes_core.sql
```

Checks:
- `SELECT to_regclass('doc'), to_regclass('chunk'), to_regclass('chunk_vec');`
- `SELECT indexname FROM pg_indexes WHERE tablename IN ('doc','hint','chunk_vec') ORDER BY 1;`

## 2) Minimal HTTP app

Run locally:

```
uvicorn web.app:app --host 127.0.0.1 --port 3011
```

Endpoints:
- `GET /api/latest?limit=50`
- `GET /api/search?q=keyword&limit=50&offset=0`
- `GET /api/search_sem?limit=20&offset=0&space=bge-m3` (fallback to recency when no `q`)
- `GET /search_sem?limit=20` (alias)

Semantic search with a JSON vector (client-side embedding):

```
curl --get --data-urlencode "q=[0.1,0.2, ... ]" \
  "http://127.0.0.1:3011/api/search_sem?limit=5&space=bge-m3"
```

When `q` is omitted the endpoint returns the latest documents as a safe fallback.

## 3) Embedding job (optional)

```
python scripts/embed_chunks.py --space bge-m3 --batch 64
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM chunk_vec WHERE embedding_space='bge-m3';"
```

## 4) Systemd (optional)

See docs/マニュアル.md for recommended EnvironmentFile and systemd unit wiring. Bind to `127.0.0.1:3011` and proxy via Nginx if needed.

