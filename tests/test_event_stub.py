import os
from datetime import datetime, timezone
import psycopg


DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/testdb")


def _conn():
    return psycopg.connect(DB_URL)


def test_event_extract_stub_creates_event_and_evidence():
    from scripts import event_extract_stub

    with _conn() as conn:
        cur = conn.cursor()
        # Insert doc + chunk with no evidence
        now = datetime.now(timezone.utc)
        url = "https://example.com/event-stub-test"
        cur.execute(
            """
            INSERT INTO doc (source, url_canon, title_raw, published_at, first_seen_at, raw)
            VALUES (%s,%s,%s,%s, now(), %s)
            ON CONFLICT (url_canon) DO NOTHING
            RETURNING doc_id
            """,
            ("test://event", url, "Event Stub Title", now, {"k": "v"}),
        )
        row = cur.fetchone()
        if row:
            doc_id = row[0]
        else:
            doc_id = cur.execute("SELECT doc_id FROM doc WHERE url_canon=%s", (url,)).fetchone()[0]
        cur.execute(
            "INSERT INTO chunk (doc_id, part_ix, text_raw, span, lang, created_at) VALUES (%s,0,%s,NULL,%s, now()) ON CONFLICT DO NOTHING",
            (doc_id, "Company X announced something.", "en"),
        )
        cid = cur.execute("SELECT chunk_id FROM chunk WHERE doc_id=%s AND part_ix=0", (doc_id,)).fetchone()[0]
        conn.commit()

    # Execute stub
    event_extract_stub.main()

    # Verify event + evidence
    with _conn() as conn:
        ev_cnt = conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE chunk_id=%s",
            (cid,),
        ).fetchone()[0]
        assert ev_cnt >= 1

