import os
from datetime import datetime, timezone
import psycopg

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/testdb")

def _conn():
    return psycopg.connect(DB_URL)

def test_schema_tables_exist():
    with _conn() as conn:
        cur = conn.cursor()
        for t in ("doc", "chunk", "chunk_vec", "hint"):
            row = cur.execute("SELECT to_regclass(%s)", (t,)).fetchone()
            assert row[0] is not None, f"table {t} missing"

def test_insert_and_doc_head():
    from mcp_news import server
    now = datetime.now(timezone.utc)
    with _conn() as conn:
        cur = conn.cursor()
        row = cur.execute(
            '''
            INSERT INTO doc (source, url_canon, title_raw, published_at, first_seen_at, raw)
            VALUES (%s,%s,%s,%s, now(), %s)
            ON CONFLICT (url_canon) DO NOTHING
            RETURNING doc_id
            ''',
            ("test://unit", "https://example.com/x", "Unit Test Title", now, {"k": "v"})
        ).fetchone()
        doc_id = row[0] if row else cur.execute("SELECT doc_id FROM doc WHERE url_canon=%s", ("https://example.com/x",)).fetchone()[0]
        cur.execute(
            "INSERT INTO chunk (doc_id, part_ix, text_raw, span, lang, created_at) VALUES (%s,0,%s,NULL,%s, now()) ON CONFLICT DO NOTHING",
            (doc_id, "Unit Test Title\n\nBody", "en"),
        )
        conn.commit()

    head = server.doc_head(doc_id)
    assert head["doc_id"] == doc_id
    assert "Unit Test Title" in head["title"]
    assert head["published_at"].endswith("Z") or "+" in head["published_at"]

def test_semantic_search_fallback():
    from mcp_news import server
    res = server.semantic_search("anything", top_k=5)
    assert isinstance(res, list)
    assert len(res) >= 1
    assert "title" in res[0] and "published_at" in res[0]
