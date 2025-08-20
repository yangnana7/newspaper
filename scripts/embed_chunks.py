#!/usr/bin/env python3
import argparse
import os
import sys
from typing import List, Tuple

import psycopg
from pgvector.psycopg import register_vector

MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
_model = None


def load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def fetch_chunks(conn, space: str, limit: int) -> List[Tuple[int, str]]:
    sql = (
        """
        SELECT c.chunk_id, c.text_raw
        FROM chunk c
        LEFT JOIN chunk_vec v ON (v.chunk_id = c.chunk_id AND v.embedding_space = %s)
        WHERE v.chunk_id IS NULL
        ORDER BY c.chunk_id ASC
        LIMIT %s
        """
    )
    return list(conn.execute(sql, (space, limit)))


def main():
    ap = argparse.ArgumentParser(description="Embed chunks into chunk_vec (pgvector)")
    ap.add_argument("--space", required=True, help="embedding_space label (e.g., bge-m3/e5-multilingual)")
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
    model = load_model()

    with psycopg.connect(dsn) as conn:
        register_vector(conn)
        conn.execute("SET TIME ZONE 'UTC'")
        while True:
            rows = fetch_chunks(conn, args.space, args.batch)
            if not rows:
                print("[✓] no pending chunks")
                break
            ids = [r[0] for r in rows]
            texts = [r[1] for r in rows]
            embs = model.encode(texts, normalize_embeddings=True)
            dim = len(embs[0]) if len(embs) else 0
            with conn.transaction():
                for cid, vec in zip(ids, embs):
                    conn.execute(
                        """
                        INSERT INTO chunk_vec (chunk_id, embedding_space, dim, emb)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (chunk_id, embedding_space) DO NOTHING
                        """,
                        (cid, args.space, dim, list(map(float, vec))),
                    )
            print(f"[+] inserted: {len(ids)} (space={args.space}, dim={dim})")


if __name__ == "__main__":
    main()

