#!/usr/bin/env python3
"""
Cluster near-duplicate documents by SimHash on titles and store cluster IDs.
Creates table dup_cluster(doc_id INT PRIMARY KEY, cluster_id BIGINT) when missing.
"""
import os
import psycopg
from typing import List, Tuple

from search.near_duplicate import cluster_by_simhash


def _connect():
    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    return psycopg.connect(dsn)


def ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dup_cluster (
            doc_id    INTEGER PRIMARY KEY,
            cluster_id BIGINT NOT NULL
        )
        """
    )


def run(limit: int = 2000, threshold: int = 3) -> int:
    with _connect() as conn:
        ensure_table(conn)
        rows: List[Tuple[int, str]] = conn.execute(
            "SELECT doc_id, COALESCE(title_raw,'') FROM doc ORDER BY doc_id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        clusters = cluster_by_simhash(rows, threshold=threshold)
        # Flatten and upsert
        n = 0
        for cid, doc_ids in clusters.items():
            for doc_id in doc_ids:
                conn.execute(
                    "INSERT INTO dup_cluster (doc_id, cluster_id) VALUES (%s, %s) ON CONFLICT (doc_id) DO UPDATE SET cluster_id=excluded.cluster_id",
                    (doc_id, cid),
                )
                n += 1
        # Optional metric: dup ratio
        try:
            total = len(rows) or 1
            multi = sum(1 for v in clusters.values() if len(v) > 1)
            ratio = float(multi) / float(total)
            from mcp_news.metrics import set_dup_ratio
            set_dup_ratio(ratio)
        except Exception:
            pass
        return n


if __name__ == "__main__":
    m = run()
    print(f"dup_rows_written={m}")

