# newspaper

## Quickstart

- Python 3.11+
- Install: `pip install -r requirements.txt`
- DB: start Postgres 16 with pgvector, then apply schema: `psql "$DATABASE_URL" -f db/schema_v2.sql`
- Ingest a few docs (examples):
  - RSS: `python scripts/ingest_rss.py --feeds config/feeds.sample.json`
  - HN: `python scripts/ingest_hn.py --kind topstories --limit 50`
  - NewsAPI: `NEWSAPI_KEY=... python scripts/ingest_newsapi.py --mode top --country jp`
- Embed (multilingual default): `python scripts/embed_chunks.py --space e5-multilingual --normalize`
- MCP server (stdio): `python -m mcp_news.server`  (uses `EMBED_SPACE`/`EMBEDDING_SPACE`, default `e5-multilingual`)
- Tests: `pytest -q`

### Web app (HTTP UI)

- Dependencies are in `requirements.txt` (includes `fastapi` and `uvicorn`).
- Run locally (bind to localhost only):
  - `mkdir -p web/static`
  - `UI_ENABLED=1 uvicorn web.app:app --host 127.0.0.1 --port 3011`
  - Note: UI is disabled by default (MCP-First). Set `UI_ENABLED=1` to enable `/` during development; otherwise `/` returns 404. API endpoints are always available.
- Endpoints:
  - `GET /api/latest?limit=50`
  - `GET /api/search?q=keyword&limit=50&offset=0`
  - `GET /api/search_sem?limit=20&offset=0&space=bge-m3` (q omitted → recency fallback)
  - alias: `GET /search_sem` (same as above)

## Notes (2025-08-21)

- Schema adds helpful indexes: `idx_doc_url` (doc.url_canon), `idx_hint_key` (hint.key)
- Optional column `doc.author` added; NewsAPI/HN/RSS ingest now stores author when available
- Implemented minimal entity linking stub (`scripts/entity_link_stub.py`) and a test
- CI runs in `.github/workflows/ci.yml` and applies schema before tests
  - Vector column: `chunk_vec.emb` uses `vector(768)` (cosine HNSW). If you change models with different dims, adjust this column and indexes accordingly.
  - CI runs tests with `PYTHONPATH=.` to ensure `scripts.*` imports work from repo root.
  - CI collects tests only from `tests/` (excludes `docs/ci_pack/tests` to avoid duplicate names).
 - Python 3.11 compat: MCP tools return `TypedDict` via `typing_extensions.TypedDict` for Pydantic schema generation.
