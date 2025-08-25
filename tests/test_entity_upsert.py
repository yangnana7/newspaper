import os
import pytest


@pytest.mark.skipif(os.getenv("SKIP_DB_TESTS") == "1", reason="DB not available in CI")
def test_entity_upsert_conflict_dedup(monkeypatch):
    """
    Ensure inserting the same entity name twice keeps a single entity row.
    This test requires a running Postgres with the expected schema and unique index
    uq_entity_name on (attrs->>'name').
    """
    import psycopg
    from scripts.entity_link import extract_entities
    from scripts.ingest_entities import ingest

    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")

    # Prepare: create a temporary chunk with repeated entity
    name = "テスト組織サンプル"
    text = f"{name} が発表。{name} は共同でイベントを開催。"

    with psycopg.connect(dsn) as conn:
        # Insert a doc and chunk minimally for ingest to read
        drow = conn.execute(
            """INSERT INTO doc (source, title_raw, published_at, url_canon)
                 VALUES ('test', 't', now() AT TIME ZONE 'UTC', 'u')
                 RETURNING doc_id"""
        ).fetchone()
        doc_id = drow[0]
        crow = conn.execute(
            "INSERT INTO chunk (doc_id, part_ix, text_raw) VALUES (%s, 0, %s) RETURNING chunk_id",
            (doc_id, text),
        ).fetchone()
        chunk_id = crow[0]

        # Run ingest twice to simulate duplicates
        ingest(limit=1)
        ingest(limit=1)

        # Count entities with that name
        er = conn.execute(
            "SELECT count(*) FROM entity WHERE attrs->>'name'=%s",
            (name,),
        ).fetchone()
        assert er[0] == 1

        # Cleanup created rows to not pollute subsequent runs (best-effort)
        try:
            conn.execute("DELETE FROM mention WHERE chunk_id=%s", (chunk_id,))
            conn.execute("DELETE FROM chunk WHERE chunk_id=%s", (chunk_id,))
            conn.execute("DELETE FROM doc WHERE doc_id=%s", (doc_id,))
            conn.commit()
        except Exception:
            conn.rollback()
