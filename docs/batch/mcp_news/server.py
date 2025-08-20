import os
from typing import List, Optional, TypedDict
from datetime import datetime, timezone
import zoneinfo
import psycopg
from pgvector.psycopg import register_vector
from mcp.server.fastmcp import FastMCP

# Optional local embedding for semantic_search
_MODEL = None
try:
    if os.getenv("ENABLE_SERVER_EMBEDDING", "0").lower() in ("1", "true", "yes"):
        from sentence_transformers import SentenceTransformer  # lazy import
        _MODEL = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base"))
except Exception:
    _MODEL = None  # fallback to recency if model can't be loaded

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:///newshub")
EMBED_SPACE  = os.getenv("EMBED_SPACE", "bge-m3")

JST = zoneinfo.ZoneInfo("Asia/Tokyo")

class Bundle(TypedDict):
    doc_id: int
    title: str
    published_at: str  # ISO8601
    genre_hint: Optional[str]
    url: Optional[str]

mcp = FastMCP("NewsHub")

def connect():
    conn = psycopg.connect(DATABASE_URL)
    try:
        register_vector(conn)
    except Exception:
        # pgvector not strictly required for fallback path
        pass
    return conn

def _row_to_bundle(row: psycopg.rows.Row) -> Bundle:
    # Row layout must match the SELECT order in queries below
    did, title, published_at, genre_hint, url = row
    # Return ISO8601 in UTC; clients can localize as desired
    if isinstance(published_at, datetime):
        published_iso = published_at.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    else:
        published_iso = str(published_at)
    return {
        "doc_id": int(did),
        "title": title or "",
        "published_at": published_iso,
        "genre_hint": genre_hint,
        "url": url,
    }

@mcp.tool()
def doc_head(doc_id: int) -> Bundle:
    """
    Return minimal head information for a document.
    """
    sql = """
      SELECT d.doc_id, d.title_raw, d.published_at,
             (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
             d.url_canon
      FROM doc d
      WHERE d.doc_id = %s
      LIMIT 1
    """
    with connect() as conn:
        row = conn.execute(sql, (doc_id,)).fetchone()
    if not row:
        return {"doc_id": doc_id, "title": "", "published_at": datetime.now(timezone.utc).isoformat(), "genre_hint": None, "url": None}  # type: ignore
    return _row_to_bundle(row)

@mcp.tool()
def semantic_search(q: str, top_k: int = 50, since: Optional[str] = None) -> List[Bundle]:
    """
    Vector semantic search over chunks if embedding model is available,
    otherwise recency fallback. Results are filtered to a single embedding space.
    """
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            since_dt = since_dt.astimezone(timezone.utc)
        except Exception:
            since_dt = None

    # Vector path
    if _MODEL is not None:
        try:
            q_emb = _MODEL.encode([q], normalize_embeddings=True)[0].tolist()
            cond = "AND d.published_at >= %s" if since_dt else ""
            params: list = [EMBED_SPACE]
            if since_dt:
                params.append(since_dt)
            params.extend([q_emb, top_k])
            sql = f"""
              SELECT d.doc_id, d.title_raw, d.published_at,
                     (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                     d.url_canon
              FROM chunk_vec v
              JOIN chunk c ON c.chunk_id = v.chunk_id
              JOIN doc   d ON d.doc_id   = c.doc_id
              WHERE v.embedding_space = %s {cond}
              ORDER BY v.emb <-> %s
              LIMIT %s
            """
            with connect() as conn:
                rows = conn.execute(sql, tuple(params)).fetchall()
            if rows:
                return [_row_to_bundle(r) for r in rows]
        except Exception:
            # fall through to recency
            pass

    # Fallback: recent docs
    with connect() as conn:
        cond = "WHERE d.published_at >= %s" if since_dt else ""
        params2 = [since_dt, top_k] if since_dt else [top_k]
        rows = conn.execute(f"""
          SELECT d.doc_id, d.title_raw, d.published_at,
                 (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                 d.url_canon
          FROM doc d {cond}
          ORDER BY d.published_at DESC
          LIMIT %s
        """, tuple(params2)).fetchall()
    return [_row_to_bundle(r) for r in rows]

if __name__ == "__main__":
    # stdio transport; run with: python -m mcp_news.server
    mcp.run_stdio()
