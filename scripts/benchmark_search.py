#!/usr/bin/env python3
import argparse
import json
import os
import time
from typing import Any, Dict

import psycopg
from pgvector.psycopg import register_vector


def pick_probe_vector(conn, space: str):
    row = conn.execute(
        "SELECT emb FROM chunk_vec WHERE embedding_space=%s LIMIT 1",
        (space,),
    ).fetchone()
    if not row:
        raise RuntimeError("No vector found in chunk_vec for the given space")
    return row[0]


def run_once(conn, space: str, vec, disable_index: bool) -> float:
    # Try to steer planner; not guaranteed, but indicative
    if disable_index:
        conn.execute("SET LOCAL enable_indexscan=off")
        conn.execute("SET LOCAL enable_bitmapscan=off")
    else:
        conn.execute("SET LOCAL enable_indexscan=on")
        conn.execute("SET LOCAL enable_bitmapscan=on")

    sql = (
        """
        SELECT d.doc_id, d.title_raw, d.published_at,
               (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
               d.url_canon, d.source,
               (v.emb <=> %s) AS dist
        FROM chunk_vec v
        JOIN chunk c USING(chunk_id)
        JOIN doc d USING(doc_id)
        WHERE v.embedding_space = %s
        ORDER BY dist ASC
        LIMIT 5
        """
    )
    t0 = time.perf_counter()
    conn.execute(sql, (vec, space)).fetchall()
    return (time.perf_counter() - t0) * 1000.0


def main():
    p = argparse.ArgumentParser(description="Benchmark semantic search with/without index hints")
    p.add_argument("--runs", type=int, default=50)
    p.add_argument("--space", default=os.environ.get("EMBED_SPACE") or os.environ.get("EMBEDDING_SPACE") or "e5-multilingual")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    out: Dict[str, Any] = {"runs": args.runs, "space": args.space}

    with psycopg.connect(dsn) as conn:
        register_vector(conn)
        vec = pick_probe_vector(conn, args.space)

        times_idx = []
        times_no = []
        for _ in range(args.runs):
            times_idx.append(run_once(conn, args.space, vec, disable_index=False))
        for _ in range(args.runs):
            times_no.append(run_once(conn, args.space, vec, disable_index=True))

    out["index_ms_avg"] = sum(times_idx) / len(times_idx) if times_idx else None
    out["noindex_ms_avg"] = sum(times_no) / len(times_no) if times_no else None
    out["index_ms_p50"] = sorted(times_idx)[len(times_idx)//2] if times_idx else None
    out["noindex_ms_p50"] = sorted(times_no)[len(times_no)//2] if times_no else None

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

