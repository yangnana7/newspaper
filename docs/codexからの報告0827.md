codex
Here’s what I’ve done and how to complete T4 on your DB.

What I Changed

- scripts/embed_chunks.py: Added robustness options to match T4.
    - --skip-existing, --sleep-ms, --max-retries (idempotent, throttled, retryable).
- tests/test_vector_filled_and_hnsw.py: New DB test (skips when SKIP_DB_TESTS=1).
    - Verifies chunk vs. chunk_vec parity for the target embedding_space.
    - Ensures an HNSW index exists on chunk_vec.
- docs/ops/T4-impl-log-2025-08-27.md: Execution log with adapted commands and DoD checklist.

Important Notes

- Model/DB schema uses chunk_vec(emb vector(768)) per embedding_space (not chunk.emb). T4 checks are adapted
accordingly.
- MCP-First unchanged: /metrics stays HELP, / is 404 by default.

How To Run T4 (on your Ubuntu DB host)

- Env (fixed per policy):
    - export APP_BIND_HOST=127.0.0.1 APP_BIND_PORT=3011 DATABASE_URL=postgresql://127.0.0.1/newshub
    - export EMBED_SPACE=e5-multilingual (must match server)
    - export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
- Backfill embeddings:
    - .venv/bin/python -m scripts.embed_chunks --space "$EMBED_SPACE" --normalize --batch 256 --max-retries 5
--skip-existing --sleep-ms 25
- Verify no missing (expect 0):
    - psql "$DATABASE_URL" -Atc "WITH t AS (SELECT count(*) FROM chunk), v AS (SELECT count(*) FROM chunk_vec WHERE
- Ensure HNSW index (create if missing) and analyze:
    - psql "$DATABASE_URL" -c "CREATE INDEX IF NOT EXISTS idx_chunk_vec_hnsw_e5_cos ON chunk_vec USING hnsw (emb
vector_cosine_ops) WHERE embedding_space='${EMBED_SPACE}';"
    - psql "$DATABASE_URL" -c "ANALYZE chunk_vec;"
- Confirm index usage (Index Scan, not Seq Scan):
    - see example EXPLAIN in docs/ops/T4-impl-log-2025-08-27.md (uses ORDER BY v.emb <=> q.emb on chunk_vec).
- Run the DB test locally:
    - SKIP_DB_TESTS=0 pytest -q -k "vector_filled_and_hnsw"

DoD Checklist

- No missing embeddings for EMBED_SPACE.
- HNSW present on chunk_vec (cosine ops).
- EXPLAIN shows Index Scan via HNSW (not SeqScan).
- Test test_vector_filled_and_hnsw passes.
- /metrics returns HELP, / returns 404.
- Re-runs are safe with --skip-existing.

Files

- Updated: scripts/embed_chunks.py
- Added: tests/test_vector_filled_and_hnsw.py
- Log: docs/ops/T4-impl-log-2025-08-27.md

Want me to also add a convenience SQL for counting per-space gaps or wire a systemd timer for periodic backfill?