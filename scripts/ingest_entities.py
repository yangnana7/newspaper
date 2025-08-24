#!/usr/bin/env python3
"""
Ingest entities from chunk text using scripts/entity_link.py.
DB access occurs only when this script is executed (no import-time connection).
"""
import os
from typing import List

import psycopg
from pgvector.psycopg import register_vector

from .entity_link import extract_entities


def _connect():
    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    conn = psycopg.connect(dsn)
    register_vector(conn)
    conn.execute("SET TIME ZONE 'UTC'")
    return conn


def ingest(limit: int = 1000) -> int:
    count = 0
    with _connect() as conn:
        rows = conn.execute(
            "SELECT c.chunk_id, c.text_raw FROM chunk c ORDER BY c.chunk_id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        for cid, text in rows:
            ents: List[str] = extract_entities(text or "")
            # Placeholder: simply record entities into entity table if absent
            for surf in ents:
                e = conn.execute(
                    "INSERT INTO entity (ext_id, kind, attrs) VALUES (NULL, NULL, jsonb_build_object('name', %s)) RETURNING ent_id",
                    (surf,),
                ).fetchone()
                ent_id = e[0]
                conn.execute(
                    "INSERT INTO mention (chunk_id, ent_id, span, conf) VALUES (%s, %s, NULL, 1.0) ON CONFLICT DO NOTHING",
                    (cid, ent_id),
                )
                count += 1
    return count


if __name__ == "__main__":
    n = ingest()
    print(f"ingested_entities={n}")

