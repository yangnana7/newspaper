#!/usr/bin/env python3
"""
簡易 recall@k 計測の雛形。

eval/queries.json の形式:
[
  {"q": "日銀 金利", "relevant_doc_ids": [123, 456], "since": null},
  {"q": "US CPI",   "relevant_doc_ids": [789]}
]

使い方:
  export DATABASE_URL=postgresql://localhost/newshub
  python scripts/eval_recall_stub.py --file eval/queries.json --k 10

注意: 本スクリプトは mcp_news.server と同等のSQLで検索する簡易版です。
モデル・スペース・ランク融合などは環境に合わせて調整してください。
"""
import argparse
import json
from typing import List, Dict
from datetime import datetime, timezone

import psycopg
from pgvector.psycopg import register_vector

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None


def to_utc(dt: str | None):
    if not dt:
        return None
    d = datetime.fromisoformat(dt)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def run_query(conn, model, q: str, k: int, since_iso: str | None):
    since_dt = to_utc(since_iso)
    if model is None:
        where, params = ("", [])
        if since_dt is not None:
            where = "WHERE d.published_at >= %s"
            params.append(since_dt)
        params.append(k)
        rows = conn.execute(
            f"""
            SELECT d.doc_id
            FROM doc d
            {where}
            ORDER BY d.published_at DESC
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()
        return [r[0] for r in rows]

    q_emb = model.encode([q], normalize_embeddings=True)[0]
    params = [list(map(float, q_emb)), k]
    cond = ""
    if since_dt is not None:
        cond = "AND d.published_at >= %s"
        params.insert(1, since_dt)
    rows = conn.execute(
        f"""
        SELECT DISTINCT d.doc_id
        FROM chunk_vec v
        JOIN chunk c ON c.chunk_id = v.chunk_id
        JOIN doc d   ON d.doc_id   = c.doc_id
        WHERE 1=1 {cond}
        ORDER BY v.emb <-> %s
        LIMIT %s
        """,
        tuple(params),
    ).fetchall()
    return [r[0] for r in rows]


def recall_at_k(rels: List[int], hits: List[int]) -> float:
    if not rels:
        return 0.0
    hit = len(set(rels) & set(hits))
    return hit / float(len(rels))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--model", default="intfloat/multilingual-e5-base")
    args = ap.parse_args()

    model = None
    if SentenceTransformer is not None:
        try:
            model = SentenceTransformer(args.model)
        except Exception:
            model = None

    with psycopg.connect() as conn:
        register_vector(conn)
        with open(args.file, "r", encoding="utf-8") as f:
            queries: List[Dict] = json.load(f)

        scores = []
        for q in queries:
            hits = run_query(conn, model, q["q"], args.k, q.get("since"))
            r = recall_at_k(q.get("relevant_doc_ids", []), hits)
            scores.append(r)
        if scores:
            avg = sum(scores) / len(scores)
        else:
            avg = 0.0
        print(f"recall@{args.k} = {avg:.3f} (n={len(scores)})")


if __name__ == "__main__":
    main()

