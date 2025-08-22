from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os, json, math, psycopg
from datetime import timezone
import zoneinfo
from typing import Optional, Dict
from pgvector.psycopg import Vector, register_vector

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


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default


def _load_source_trust() -> Dict[str, float]:
    raw = os.environ.get("SOURCE_TRUST_JSON", "")
    if not raw:
        return {}
    try:
        m = json.loads(raw)
        if isinstance(m, dict):
            out: Dict[str, float] = {}
            for k, v in m.items():
                try:
                    out[str(k)] = float(v)
                except Exception:
                    continue
            return out
    except Exception:
        pass
    return {}


def _recency_decay(published_at, halflife_h: float) -> float:
    try:
        dt = published_at.astimezone(timezone.utc)
        age_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
        if halflife_h <= 0:
            return 0.0
        return 0.5 ** (age_h / halflife_h)
    except Exception:
        return 0.0

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
    space: str = Query(os.environ.get("EMBED_SPACE") or os.environ.get("EMBEDDING_SPACE") or "bge-m3"),
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
                    # fusion params
                    a = _env_float("RANK_ALPHA", 0.7)
                    b = _env_float("RANK_BETA", 0.2)
                    g = _env_float("RANK_GAMMA", 0.1)
                    ssum = a + b + g
                    if ssum <= 0:
                        a, b, g = 1.0, 0.0, 0.0
                        ssum = 1.0
                    a, b, g = a / ssum, b / ssum, g / ssum
                    hl = _env_float("RECENCY_HALFLIFE_HOURS", 24.0)
                    trust_map = _load_source_trust()
                    trust_default = _env_float("SOURCE_TRUST_DEFAULT", 1.0)

                    scored = []
                    for r in rows:
                        dist = float(r[6]) if r[6] is not None else 1.0
                        cos_sim = 1.0 - max(0.0, min(1.0, dist))
                        rec = _recency_decay(r[2], hl)
                        trust = float(trust_map.get(r[5], trust_default))
                        score = a * cos_sim + b * rec + g * trust
                        scored.append((score, r))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    return [row_to_dict(sr[1]) for sr in scored[:limit]]
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
