## 6) 仕上げ手順（人間向け・貼るだけOK）

```bash
# 1) バックフィル
.venv/bin/python -m scripts.embed_chunks --space e5-multilingual --normalize --batch 256 --max-retries 5 --skip-existing --sleep-ms 25

確認結果：
$ .venv/bin/python -m scripts.embed_chunks --space e5-multilingual --normalize --batch 256 --max-retries 5 --skip-existing --sleep-ms 25
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/yang_server/newspaper/scripts/embed_chunks.py", line 96, in <module>
    main()
  File "/home/yang_server/newspaper/scripts/embed_chunks.py", line 51, in main
    with psycopg.connect(dsn) as conn:
         ^^^^^^^^^^^^^^^^^^^^
  File "/home/yang_server/newspaper/.venv/lib/python3.12/site-packages/psycopg/connection.py", line 118, in connect
    raise last_ex.with_traceback(None)
psycopg.OperationalError: connection failed: connection to server at "127.0.0.1", port 5432 failed: fe_sendauth: no password supplied

# 2) 欠損0の確認
psql "$DATABASE_URL" -Atc "SELECT count(*) FROM chunk WHERE emb IS NULL"

確認結果：
$ psql "$DATABASE_URL" -Atc "SELECT count(*) FROM chunk WHERE emb IS NULL"
psql: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL:  database "yang_server" does not exist

# 3) HNSW作成（無ければ）
psql "$DATABASE_URL" -c "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunk_emb_hnsw_cos ON chunk USING hnsw (emb vector_cos_ops) WITH (m=16, ef_construction=64);"
作業ログ：
$ psql "$DATABASE_URL" -c "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunk_emb_hnsw_cos ON chunk USING hnsw (emb vector_cos_ops) WITH (m=16, ef_construction=64);"
psql: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL:  database "yang_server" does not exist

psql "$DATABASE_URL" -c "ANALYZE chunk;"
作業ログ：
$ psql "$DATABASE_URL" -c "ANALYZE chunk;"
psql: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL:  database "yang_server" does not exist

# 4) EXPLAINでIndex使用確認（目視）
psql "$DATABASE_URL" -c "EXPLAIN (ANALYZE, COSTS, VERBOSE, BUFFERS, TIMING) WITH q AS (SELECT emb FROM chunk WHERE emb IS NOT NULL ORDER BY chunk_id DESC LIMIT 1) SELECT c.chunk_id FROM chunk c, q ORDER BY c.emb <=> q.emb LIMIT 10;"
確認結果：
$ psql "$DATABASE_URL" -c "EXPLAIN (ANALYZE, COSTS, VERBOSE, BUFFERS, TIMING) WITH q AS (SELECT emb FROM chunk WHERE emb IS NOT NULL ORDER BY chunk_id DESC LIMIT 1) SELECT c.chunk_id FROM chunk c, q ORDER BY c.emb <=> q.emb LIMIT 10;"
psql: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL:  database "yang_server" does not exist

# 5) ローカル回帰テスト（DBあり）
SKIP_DB_TESTS=0 pytest -q -k "vector_filled_and_hnsw"
確認結果：
$ SKIP_DB_TESTS=0 pytest -q -k "vector_filled_and_hnsw"

3 skipped, 30 deselected in 0.15s