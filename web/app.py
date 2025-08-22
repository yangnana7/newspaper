from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os, psycopg
from datetime import timezone
import zoneinfo

JST = zoneinfo.ZoneInfo("Asia/Tokyo")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1:5432/newshub")

app = FastAPI(title="MCP News – Minimal UI")
app.mount("/static", StaticFiles(directory="web/static"), name="static")

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

# （任意）超簡易タイトル検索（PGroongaなしでも ILIKE で動く）
@app.get("/api/search")
def api_search(q: str, limit: int = Query(50, ge=1, le=200)):
    sql = """
      SELECT d.doc_id, d.title_raw, d.published_at,
             (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
             d.url_canon, d.source
      FROM doc d
      WHERE d.title_raw ILIKE %s
      ORDER BY d.published_at DESC
      LIMIT %s
    """
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, (f"%{q}%", limit)).fetchall()
    return [row_to_dict(r) for r in rows]

# セマンティック検索（ベクトル検索またはフォールバック）
@app.get("/api/search_sem")
def api_search_sem(
    q: str = Query(None, description="Query vector as JSON array or empty for latest"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    space: str = Query("bge-m3", description="Embedding space")
):
    if q is None or q.strip() == "":
        # フォールバック：新着順
        sql = """
          SELECT d.doc_id, d.title_raw, d.published_at,
                 (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                 d.url_canon, d.source
          FROM doc d
          ORDER BY d.published_at DESC
          LIMIT %s OFFSET %s
        """
        with psycopg.connect(DATABASE_URL) as conn:
            rows = conn.execute(sql, (limit, offset)).fetchall()
        return [row_to_dict(r) for r in rows]
    
    try:
        # ベクトル検索を試行
        import json
        query_vector = json.loads(q)
        if not isinstance(query_vector, list) or len(query_vector) == 0:
            raise ValueError("Invalid vector format")
        
        sql = """
          SELECT d.doc_id, d.title_raw, d.published_at,
                 (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
                 d.url_canon, d.source,
                 (cv.emb <=> %s::vector) AS similarity
          FROM doc d
          JOIN chunk c ON d.doc_id = c.doc_id
          JOIN chunk_vec cv ON c.chunk_id = cv.chunk_id
          WHERE cv.embedding_space = %s
          ORDER BY similarity
          LIMIT %s OFFSET %s
        """
        
        with psycopg.connect(DATABASE_URL) as conn:
            rows = conn.execute(sql, (query_vector, space, limit, offset)).fetchall()
        
        # similarity列を除いてレスポンス作成
        results = []
        for r in rows:
            # r: doc_id, title_raw, published_at, genre_hint, url_canon, source, similarity
            ts = r[2].astimezone(JST).isoformat(timespec="seconds")
            results.append({
                "doc_id": r[0], "title": r[1], "published_at": ts,
                "genre_hint": r[3], "url": r[4], "source": r[5]
            })
        return results
        
    except (ValueError, json.JSONDecodeError, Exception):
        # エラー時は空配列を返す（qが指定されている場合フォールバックしない）
        return []

# ルート：静的HTML
@app.get("/", response_class=HTMLResponse)
def index():
    with open("web/templates/index.html", "r", encoding="utf-8") as f:
        return f.read()
