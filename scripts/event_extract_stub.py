#!/usr/bin/env python3
"""
Event extraction stub (minimal):
- For each chunk without evidence, create a dummy event (type_id='stub:event').
- Link the chunk/doc to the event via evidence.
"""
import os
from typing import List, Tuple

import psycopg


def fetch_unprocessed_chunks(conn: psycopg.Connection, limit: int = 200) -> List[Tuple[int, int]]:
    sql = (
        """
        SELECT c.chunk_id, c.doc_id
        FROM chunk c
        LEFT JOIN evidence ev ON ev.chunk_id = c.chunk_id
        WHERE ev.chunk_id IS NULL
        ORDER BY c.chunk_id ASC
        LIMIT %s
        """
    )
    return list(conn.execute(sql, (limit,)))


def create_event_for_chunk(conn: psycopg.Connection, chunk_id: int, doc_id: int) -> None:
    cur = conn.execute(
        """
        INSERT INTO event (type_id, t_start, t_end, loc_geohash, attrs)
        VALUES ('stub:event', NULL, NULL, NULL, NULL)
        RETURNING event_id
        """
    )
    ev_id = cur.fetchone()[0]
    conn.execute(
        """
        INSERT INTO evidence (event_id, doc_id, chunk_id, weight)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (ev_id, doc_id, chunk_id, 0.1),
    )


def process(limit: int = 200) -> int:
    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
    inserted = 0
    with psycopg.connect(dsn) as conn:
        conn.execute("SET TIME ZONE 'UTC'")
        rows = fetch_unprocessed_chunks(conn, limit)
        for cid, did in rows:
            with conn.transaction():
                create_event_for_chunk(conn, cid, did)
                inserted += 1
    return inserted


def main():
    n = process()
    print(f"[i] event_extract_stub: inserted events={n}")


if __name__ == "__main__":
    main()
