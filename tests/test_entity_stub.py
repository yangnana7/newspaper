import os
import psycopg
from datetime import datetime, timezone


DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/testdb")


def _conn():
    return psycopg.connect(DB_URL)


def test_entity_link_stub_inserts_mentions():
    from scripts import entity_link_stub

    with _conn() as conn:
        cur = conn.cursor()
        # Insert a fresh doc + chunk
        now = datetime.now(timezone.utc)
        url = "https://example.com/entity-stub-test"
        cur.execute(
            """
            INSERT INTO doc (source, url_canon, title_raw, published_at, first_seen_at, raw)
            VALUES (%s,%s,%s,%s, now(), %s)
            ON CONFLICT (url_canon) DO NOTHING
            RETURNING doc_id
            """,
            ("test://entity", url, "Entity Stub Title", now, {"k": "v"}),
        )
        row = cur.fetchone()
        if row:
            doc_id = row[0]
        else:
            doc_id = cur.execute("SELECT doc_id FROM doc WHERE url_canon=%s", (url,)).fetchone()[0]
        cur.execute(
            "INSERT INTO chunk (doc_id, part_ix, text_raw, span, lang, created_at) VALUES (%s,0,%s,NULL,%s, now()) ON CONFLICT DO NOTHING",
            (doc_id, "OpenAI builds models in Tokyo. Apple releases products.", "en"),
        )
        cid = cur.execute("SELECT chunk_id FROM chunk WHERE doc_id=%s AND part_ix=0", (doc_id,)).fetchone()[0]
        conn.commit()

    # Run stub to process chunks
    entity_link_stub.main()

    # Verify mentions were inserted for our chunk
    with _conn() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM mention WHERE chunk_id=%s", (cid,)).fetchone()[0]
        assert cnt >= 1

