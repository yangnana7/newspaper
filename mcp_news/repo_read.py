from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    from pgvector.psycopg import Vector  # type: ignore
except Exception:  # pragma: no cover
    Vector = None  # type: ignore

from .db import connect
from .settings import Settings


DocHead = Dict[str, Any]


def get_recent_docs(limit: int = 50) -> List[DocHead]:
    sql = (
        """
        SELECT d.doc_id, d.title_raw, d.published_at,
               (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
               d.url_canon, d.source
        FROM doc d
        ORDER BY d.published_at DESC
        LIMIT %s
        """
    )
    with connect() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
        return [
            {
                "doc_id": r[0],
                "title": r[1],
                "published_at": r[2],
                "genre_hint": r[3],
                "url": r[4],
                "source": r[5],
            }
            for r in rows
        ]


def search_semantic_head(q_vec: List[float], top_k: int) -> List[Tuple[Any, ...]]:
    """Return candidate rows similar to q_vec ordered by cosine distance.
    The returned tuples mirror (doc_id, title_raw, published_at, genre_hint, url_canon, source, lang, dist).
    """
    if Vector is None:
        return []
    space = Settings().embedding_space
    cand = min(200, max(top_k * 3 + 10, top_k))
    qv = Vector(list(map(float, q_vec)))
    sql = (
        """
        SELECT d.doc_id, d.title_raw, d.published_at,
               (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
               d.url_canon, d.source, d.lang,
               (v.emb <=> %s) AS dist
        FROM chunk_vec v
        JOIN chunk c USING(chunk_id)
        JOIN doc   d USING(doc_id)
        WHERE v.embedding_space = %s
        ORDER BY dist ASC
        LIMIT %s
        """
    )
    with connect() as conn:
        return conn.execute(sql, (qv, space, cand)).fetchall()

