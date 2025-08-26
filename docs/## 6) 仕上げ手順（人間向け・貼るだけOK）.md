## 6) 仕上げ手順（人間向け・貼るだけOK）

```bash
# 1) バックフィル
.venv/bin/python -m scripts.embed_chunks --space e5-multilingual --normalize --batch 256 --max-retries 5 --skip-existing --sleep-ms 25

# 2) 欠損0の確認
psql "$DATABASE_URL" -Atc "SELECT count(*) FROM chunk WHERE emb IS NULL"

# 3) HNSW作成（無ければ）
psql "$DATABASE_URL" -c "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunk_emb_hnsw_cos ON chunk USING hnsw (emb vector_cos_ops) WITH (m=16, ef_construction=64);"
psql "$DATABASE_URL" -c "ANALYZE chunk;"

# 4) EXPLAINでIndex使用確認（目視）
psql "$DATABASE_URL" -c "EXPLAIN (ANALYZE, COSTS, VERBOSE, BUFFERS, TIMING) WITH q AS (SELECT emb FROM chunk WHERE emb IS NOT NULL ORDER BY chunk_id DESC LIMIT 1) SELECT c.chunk_id FROM chunk c, q ORDER BY c.emb <=> q.emb LIMIT 10;"

# 5) ローカル回帰テスト（DBあり）
SKIP_DB_TESTS=0 pytest -q -k "vector_filled_and_hnsw"
```