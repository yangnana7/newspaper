from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os, json, psycopg
from datetime import timezone
import zoneinfo
from typing import Optional
from pgvector.psycopg import Vector, register_vector
from search.ranker import rerank_candidates

JST = zoneinfo.ZoneInfo("Asia/Tokyo")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")

app = FastAPI(title="MCP News – Minimal UI")
# Avoid startup failure when static dir is absent during tests/CI
app.mount("/static", StaticFiles(directory="web/static", check_dir=False), name="static")

def row_to_dict(r):
    # r: doc_id, title_raw, published_at(UTC), genre_hint, url_canon, source
    ts = r[2].astimezone(JST).isoformat(timespec="seconds")
    return {"doc_id": r[0], "title": r[1], "published_at": ts,
            "genre_hint": r[3], "url": r[4], "source": r[5]}


@app.get("/api/latest")
def api_latest(limit: int = Query(50, ge=1, le=200)):
    sql = """
      SELECT d.doc_id, d.title_raw, d.published_at,
             (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
             d.url_canon, d.source
      FROM doc d
      ORDER BY d.published_at DESC
      LIMIT %s
    """
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    return [row_to_dict(r) for r in rows]

# シンプルなタイトル検索（ILIKE）。source/期間/offsetを追加。
@app.get("/api/search")
def api_search(
    q: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: Optional[str] = None,
    since_days: Optional[int] = Query(None, ge=0),
):
    conds = ["d.title_raw ILIKE %s"]
    params = [f"%{q}%"]
    if source:
        conds.append("d.source = %s")
        params.append(source)
    if since_days is not None:
        conds.append("d.published_at >= (now() AT TIME ZONE 'UTC') - (%s || ' days')::interval")
        params.append(since_days)
    params.extend([limit, offset])
    sql = f"""
      SELECT d.doc_id, d.title_raw, d.published_at,
             (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
             d.url_canon, d.source
      FROM doc d
      WHERE {' AND '.join(conds)}
      ORDER BY d.published_at DESC
      LIMIT %s OFFSET %s
    """
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [row_to_dict(r) for r in rows]

# セマンティック検索（cosine距離 <=>）。q は JSON 数値配列（暫定）。
@app.get("/api/search_sem")
@app.get("/search_sem")
def api_search_sem(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    space: str = Query(os.environ.get("EMBED_SPACE") or os.environ.get("EMBEDDING_SPACE") or "e5-multilingual"),
    q: Optional[str] = None,
):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            register_vector(conn)
            if q:
                try:
                    vec = json.loads(q)
                except Exception:
                    vec = None
                if isinstance(vec, list) and all(isinstance(x, (int, float)) for x in vec):
                    # candidate size for fusion re-ranking
                    cand = min(200, max(limit * 3 + 10, limit))
                    sql = """
                      SELECT d.doc_id, d.title_raw, d.published_at,
                             (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                             d.url_canon, d.source,
                             (v.emb <=> %s) AS dist
                      FROM chunk_vec v
                      JOIN chunk c USING(chunk_id)
                      JOIN doc d USING(doc_id)
                      WHERE v.embedding_space = %s
                      ORDER BY dist ASC
                      LIMIT %s OFFSET %s
                    """
                    rows = conn.execute(sql, (Vector(vec), space, cand, offset)).fetchall()
                    reranked = rerank_candidates(rows, dist_index=6, published_index=2, source_index=5, limit=limit)
                    return [row_to_dict(r) for r in reranked]
            # フォールバック：最新順
            sql2 = """
              SELECT d.doc_id, d.title_raw, d.published_at,
                     (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                     d.url_canon, d.source
              FROM doc d
              ORDER BY d.published_at DESC
              LIMIT %s OFFSET %s
            """
            rows2 = conn.execute(sql2, (limit, offset)).fetchall()
            return [row_to_dict(r) for r in rows2]
    except Exception:
        # 失敗時も新着順へフォールバックを試みる
        try:
            with psycopg.connect(DATABASE_URL) as conn2:
                sqlf = """
                  SELECT d.doc_id, d.title_raw, d.published_at,
                         (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                         d.url_canon, d.source
                  FROM doc d
                  ORDER BY d.published_at DESC
                  LIMIT %s OFFSET %s
                """
                rowsf = conn2.execute(sqlf, (limit, offset)).fetchall()
                return [row_to_dict(r) for r in rowsf]
        except Exception:
            # 最後まで失敗した場合は空
            return []

# ルート：静的HTML
@app.get("/", response_class=HTMLResponse)
def index():
    with open("web/templates/index.html", "r", encoding="utf-8") as f:
        return f.read()
