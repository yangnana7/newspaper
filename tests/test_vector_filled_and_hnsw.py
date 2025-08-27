import os
import pytest

pytest.importorskip("psycopg")
import psycopg  # type: ignore


@pytest.mark.skipif(os.getenv("SKIP_DB_TESTS") == "1", reason="DB not available in CI")
def test_chunk_vec_filled_for_space_and_hnsw_present():
    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    space = os.environ.get("EMBED_SPACE") or os.environ.get("EMBEDDING_SPACE") or "e5-multilingual"
    with psycopg.connect(dsn) as conn:
        # total chunks
        t = conn.execute("SELECT count(*) FROM chunk").fetchone()[0]
        # vectors for the target space
        v = conn.execute(
            "SELECT count(*) FROM chunk_vec WHERE embedding_space=%s",
            (space,),
        ).fetchone()[0]
        # If there are any chunks, they should all be embedded for the chosen space
        assert v == t

        # Ensure at least one HNSW index exists on chunk_vec
        idx = conn.execute(
            """
            SELECT 1
            FROM pg_index i
            JOIN pg_class c ON c.oid=i.indexrelid
            JOIN pg_am am ON am.oid=c.relam
            WHERE i.indrelid='chunk_vec'::regclass
              AND amname='hnsw'
            LIMIT 1
            """
        ).fetchone()
        assert idx is not None

