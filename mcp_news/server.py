from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
try:
    # For Python < 3.12, ensure FastMCP/Pydantic can introspect TypedDict
    from typing_extensions import TypedDict  # type: ignore
except Exception:  # pragma: no cover
    from typing import TypedDict  # type: ignore

from mcp.server.fastmcp import FastMCP
import psycopg
from .db import connect
from search.ranker import rerank_candidates

# Import common metrics module
from .metrics import get_metrics_content

# Embedding space label used for vector search (must match embed_chunks --space)
# Accept both EMBED_SPACE and legacy EMBEDDING_SPACE for compatibility
EMBED_SPACE = os.environ.get("EMBED_SPACE") or os.environ.get("EMBEDDING_SPACE") or "e5-multilingual"


class Bundle(TypedDict, total=False):
    doc_id: int
    title: str
    published_at: str
    genre_hint: Optional[str]
    url: str
    evidence: List[Dict[str, Any]]
    entities: List[str]


mcp = FastMCP("MCPNews")


def _try_load_model():
    flag = os.environ.get("ENABLE_SERVER_EMBEDDING", "0").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return None
    try:
        from sentence_transformers import SentenceTransformer

        model_name = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
        return SentenceTransformer(model_name)
    except Exception:
        return None


_MODEL = _try_load_model()


def _to_iso(dt_utc: datetime) -> str:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.isoformat(timespec="seconds")


def _row_to_bundle(row: psycopg.rows.Row) -> Bundle:
    return {
        "doc_id": row[0],
        "title": row[1],
        "published_at": _to_iso(row[2]),
        "genre_hint": row[3],
        "url": row[4],
    }


@mcp.tool()
def doc_head(doc_id: int) -> Bundle:
    with connect() as conn:
        cur = conn.execute(
            """
            SELECT d.doc_id, d.title_raw, d.published_at,
                   (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                   d.url_canon
            FROM doc d
            WHERE d.doc_id=%s
            """,
            (doc_id,),
        )
        row = cur.fetchone()
        if not row:
            return {}
        return _row_to_bundle(row)


@mcp.tool()
def semantic_search(q: str, top_k: int = 50, since: Optional[str] = None) -> List[Bundle]:
    """Semantic search over chunk_vec if available; fallback to recency."""
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            since_dt = since_dt.astimezone(timezone.utc)
        except Exception:
            since_dt = None

    with connect() as conn:
        # Vector search if model is available and chunk_vec exists
        if _MODEL is not None:
            try:
                from pgvector.psycopg import Vector  # local import to avoid hard dep when unused
                q_emb = _MODEL.encode([q], normalize_embeddings=True)[0]
                cond_sql = ""
                params: List[Any] = []
                if since_dt is not None:
                    cond_sql = "AND d.published_at >= %s"
                    # will append later after space
                    pass
                qv = Vector(list(map(float, q_emb)))
                # candidate expansion for fusion re-ranking
                cand = min(200, max(top_k * 3 + 10, top_k))
                # order: qv(for dist), space, optional since, limit
                params = [qv, EMBED_SPACE] + ([since_dt] if since_dt is not None else []) + [cand]

                cur = conn.execute(
                    f"""
                    SELECT d.doc_id, d.title_raw, d.published_at,
                           (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                           d.url_canon, d.source, d.lang,
                           (v.emb <=> %s) AS dist
                    FROM chunk_vec v
                    JOIN chunk c ON c.chunk_id = v.chunk_id
                    JOIN doc d   ON d.doc_id   = c.doc_id
                    WHERE v.embedding_space = %s {cond_sql}
                    ORDER BY dist ASC
                    LIMIT %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
                if rows:
                    reranked = rerank_candidates(
                        rows,
                        dist_index=7,
                        published_index=2,
                        source_index=5,
                        language_index=6,
                        limit=top_k,
                    )
                    return [_row_to_bundle(r) for r in reranked]
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass

        # Fallback: recency
        params2: List[Any] = []
        where = ""
        if since_dt is not None:
            where = "WHERE d.published_at >= %s"
            params2.append(since_dt)
        params2.append(top_k)
        cur = conn.execute(
            f"""
            SELECT d.doc_id, d.title_raw, d.published_at,
                   (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                   d.url_canon
            FROM doc d
            {where}
            ORDER BY d.published_at DESC
            LIMIT %s
            """,
            tuple(params2),
        )
        rows = cur.fetchall()
        return [_row_to_bundle(r) for r in rows]


@mcp.tool()
def entity_search(ext_ids: List[str], top_k: int = 50) -> List[Bundle]:
    if not ext_ids:
        return []
    with connect() as conn:
        cur = conn.execute(
            """
            SELECT DISTINCT d.doc_id, d.title_raw, d.published_at,
                    (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                    d.url_canon
            FROM mention m
            JOIN entity e ON e.ent_id = m.ent_id
            JOIN chunk  c ON c.chunk_id = m.chunk_id
            JOIN doc    d ON d.doc_id   = c.doc_id
            WHERE e.ext_id = ANY(%s)
            ORDER BY d.published_at DESC
            LIMIT %s
            """,
            (ext_ids, top_k),
        )
        return [_row_to_bundle(r) for r in cur.fetchall()]


@mcp.tool()
def event_timeline(
    filter: Dict[str, Any],
    top_k: int = 200,
) -> List[Dict[str, Any]]:
    ext_id = filter.get("ext_id") if filter else None
    type_id = filter.get("type_id") if filter else None
    t_from = filter.get("time", {}).get("from") if filter else None
    t_to = filter.get("time", {}).get("to") if filter else None

    params: List[Any] = []
    where: List[str] = []
    if type_id:
        where.append("e.type_id = %s")
        params.append(type_id)
    if t_from:
        where.append("e.t_start >= %s")
        params.append(t_from)
    if t_to:
        where.append("(e.t_end IS NULL OR e.t_end <= %s)")
        params.append(t_to)
    if ext_id:
        where.append("e.event_id IN (SELECT ep.event_id FROM event_participant ep JOIN entity en ON en.ent_id=ep.ent_id WHERE en.ext_id=%s)")
        params.append(ext_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"SELECT e.event_id, e.type_id, e.t_start, e.t_end, e.loc_geohash FROM event e {where_sql} ORDER BY e.t_start NULLS LAST, e.event_id LIMIT %s"
    params.append(top_k)
    with connect() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "event_id": r[0],
                    "type_id": r[1],
                    "t_start": _to_iso(r[2]) if r[2] else None,
                    "t_end": _to_iso(r[3]) if r[3] else None,
                    "loc_geohash": r[4],
                }
            )
        return out


@mcp.tool()
def get_metrics() -> str:
    """Return Prometheus metrics in text format."""
    return get_metrics_content()


if __name__ == "__main__":
    # stdio transport
    mcp.run_stdio()
