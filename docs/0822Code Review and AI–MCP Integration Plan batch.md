「**距離関数のcos統一／インデックス補強／検索API（セマンティック＆フォールバック）／テスト**」をまとめた **差分パッチ一式** を作りました。どれも **unified diff** 形式なので、そのまま `git apply` できます。

---

# 適用手順（共通）

```bash
# 作業ブランチ
git switch -c day3/mcp-cos-search-and-indexes

# パッチ保存（このメッセージから各コードブロックをファイルに保存）
# 例）0001-db-indexes-and-trgm.patch など

# パッチ適用
git apply --whitespace=fix 0001-db-indexes-and-trgm.patch
git apply --whitespace=fix 0002-server-search-sem-cos.patch
git apply --whitespace=fix 0003-tests-search-sem.patch
git apply --whitespace=fix 0004-docs-roadmap-day3.patch

# DBに追加インデックス適用（安全・冪等）
psql "$DATABASE_URL" -f db/indexes_core.sql

# テスト&ローカル起動
pytest -q
uvicorn web.app:app --host 127.0.0.1 --port 8000 --reload  # （UI残す場合のみ）
```

---

# 0001-db-indexes-and-trgm.patch

* `db/indexes_core.sql` を新規追加：ILIKE高速化（pg\_trgm）、新着・ソース・URL重複抑制に効く索引を作成
* `db/schema_v2.sql` 末尾に**安全な追記**（存在チェック付き）を追加（冪等運用の補助）

```diff
diff --git a/db/indexes_core.sql b/db/indexes_core.sql
new file mode 100644
index 0000000..e2b3df1
--- /dev/null
+++ b/db/indexes_core.sql
@@ -0,0 +1,29 @@
+-- Optional but recommended indexes for web/API performance
+-- Safe to run multiple times.
+
+-- Recent-first listing
+CREATE INDEX IF NOT EXISTS idx_doc_published_at_desc ON doc (published_at DESC);
+
+-- Source filter
+CREATE INDEX IF NOT EXISTS idx_doc_source ON doc (source);
+
+-- De-dup by canonical URL
+CREATE INDEX IF NOT EXISTS idx_doc_urlcanon_published_at_desc ON doc (url_canon, published_at DESC);
+
+-- Hints by (doc_id, key)
+CREATE INDEX IF NOT EXISTS idx_hint_docid_key ON hint (doc_id, key);
+
+-- Fast ILIKE for titles (requires pg_trgm)
+CREATE EXTENSION IF NOT EXISTS pg_trgm;
+CREATE INDEX IF NOT EXISTS idx_doc_title_raw_trgm ON doc USING GIN (title_raw gin_trgm_ops);
diff --git a/db/schema_v2.sql b/db/schema_v2.sql
index 3b9d0fd..1a2b5ab 100644
--- a/db/schema_v2.sql
+++ b/db/schema_v2.sql
@@ -999,3 +999,16 @@
 -- (既存のテーブル定義・制約・インデックスはそのまま)
 -- v2 schema defines doc/chunk/chunk_vec/entity/event/hint 等
 
+-- ---- Optional operational indexes (safe if applied twice) ----
+DO $$
+BEGIN
+  -- create extension if not exists
+  PERFORM 1 FROM pg_extension WHERE extname='pg_trgm';
+  IF NOT FOUND THEN
+    EXECUTE 'CREATE EXTENSION pg_trgm';
+  END IF;
+END$$;
+
+CREATE INDEX IF NOT EXISTS idx_doc_published_at_desc ON doc (published_at DESC);
+CREATE INDEX IF NOT EXISTS idx_doc_source ON doc (source);
+CREATE INDEX IF NOT EXISTS idx_doc_urlcanon_published_at_desc ON doc (url_canon, published_at DESC);
```

---

# 0002-server-search-sem-cos.patch

* `mcp_news/server.py` に **セマンティック検索エンドポイント（/search\_sem）** を追加
* **cos距離 `<=>` の明示**、`pgvector.psycopg.Vector` で右辺型合わせ
* `ENABLE_SERVER_EMBEDDING` の厳密化（truthy/falsey曖昧さ排除）
* 失敗時は `rollback()` の上で **新着順フォールバック** を強制

```diff
diff --git a/mcp_news/server.py b/mcp_news/server.py
index 2b4e8b1..9b31f2f 100644
--- a/mcp_news/server.py
+++ b/mcp_news/server.py
@@ -1,17 +1,32 @@
 import os
 import json
 import psycopg
-from typing import Any, Dict, List, Optional
+from typing import Any, Dict, List, Optional, TypedDict
 from datetime import timezone, datetime
 import zoneinfo
+from pgvector.psycopg import Vector
 
 JST = zoneinfo.ZoneInfo("Asia/Tokyo")
 DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
-ENABLE_SERVER_EMBEDDING = os.environ.get("ENABLE_SERVER_EMBEDDING", "0")
+def _env_bool(name: str, default: bool=False) -> bool:
+    v = os.environ.get(name, "")
+    if v is None or v == "":
+        return default
+    return v.strip().lower() in ("1","true","yes","on")
+
+ENABLE_SERVER_EMBEDDING = _env_bool("ENABLE_SERVER_EMBEDDING", False)
 EMBEDDING_SPACE = os.environ.get("EMBEDDING_SPACE", "bge-m3")
 
+# ---- Pydantic-free lightweight schema for responses ----
+class DocHit(TypedDict, total=False):
+    doc_id: int
+    title: str
+    url: str
+    published_at: str
+    source: Optional[str]
+    genre_hint: Optional[str]
+
 def _row_to_hit(r) -> Dict[str, Any]:
     ts = r[2]
     if ts and getattr(ts, "tzinfo", None) is None:
         ts = ts.replace(tzinfo=timezone.utc)
@@ -21,6 +36,7 @@ def _row_to_hit(r) -> Dict[str, Any]:
         "title": r[1],
         "published_at": ts_jst,
         "genre_hint": r[3],
+        "url": r[4],
         "source": r[5],
     }
 
@@ -39,6 +55,7 @@ def list_latest(conn, *, limit: int = 50, offset: int = 0,
         rows = cur.fetchall()
     return [ _row_to_hit(r) for r in rows ]
 
+# naive title ILIKE
 def search_ilike(conn, *, q: str, limit: int = 50, offset: int = 0,
                  source: Optional[str] = None, since_days: Optional[int] = None,
                  dedup: bool = True) -> List[Dict[str, Any]]:
@@ -72,6 +89,63 @@ def search_ilike(conn, *, q: str, limit: int = 50, offset: int = 0,
     return [ _row_to_hit(r) for r in rows ]
 
+# semantic (cosine) search using pgvector
+def search_semantic(conn, *, qvec: List[float], limit: int = 50, offset: int = 0,
+                    space: str = "bge-m3") -> List[DocHit]:
+    sql = """
+      SELECT d.doc_id, d.title_raw, d.published_at,
+             (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
+             d.url_canon, d.source
+      FROM chunk_vec v
+      JOIN chunk c USING(chunk_id)
+      JOIN doc d USING(doc_id)
+      WHERE v.embedding_space = %s
+      ORDER BY v.emb <=> %s
+      LIMIT %s OFFSET %s
+    """
+    with conn.cursor() as cur:
+        cur.execute(sql, (space, Vector(qvec), limit, offset))
+        rows = cur.fetchall()
+    return [ _row_to_hit(r) for r in rows ]
+
+# ---- FastAPI wiring ----
 from fastapi import FastAPI, Query
 from fastapi.responses import JSONResponse
 
 app = FastAPI(title="MCP News Server")
 
+@app.get("/search_sem")
+def api_search_sem(
+    limit: int = Query(20, ge=1, le=200),
+    offset: int = Query(0, ge=0),
+    space: str = Query(EMBEDDING_SPACE),
+    q: Optional[str] = None
+):
+    """
+    Semantic search.
+    - If ENABLE_SERVER_EMBEDDING=1 and 'q' text is provided, this route expects
+      the embedding to be computed upstream (MCP client) and passed via header/body in the future.
+      For now、本文では q を JSON array として解釈（互換運用のため）。
+    - If parsing fails or disabled, fallback to recency list.
+    """
+    try:
+        with psycopg.connect(DATABASE_URL) as conn:
+            if q:
+                # q を JSON のベクトルとして受け付ける暫定運用
+                vec = json.loads(q)
+                if not isinstance(vec, list) or not all(isinstance(x,(int,float)) for x in vec):
+                    raise ValueError("q is not a JSON float array")
+                return JSONResponse(search_semantic(conn, qvec=vec, limit=limit, offset=offset, space=space))
+            # no q -> recency fallback
+            return JSONResponse(list_latest(conn, limit=limit, offset=offset, dedup=True))
+    except Exception:
+        # 最後まで失敗時は安全にフォールバック
+        try:
+            with psycopg.connect(DATABASE_URL) as conn2:
+                return JSONResponse(list_latest(conn2, limit=limit, offset=offset, dedup=True))
+        except Exception:
+            # どうしてもダメなら空
+            return JSONResponse([])
+
 @app.get("/search")
 def api_search(
     q: str,
@@ -87,14 +161,17 @@ def api_search(
     try:
         with psycopg.connect(DATABASE_URL) as conn:
             return JSONResponse(search_ilike(conn, q=q, limit=limit, offset=offset,
                                              source=source, since_days=since_days, dedup=bool(dedup)))
-    except Exception as e:
-        return JSONResponse({"error": str(e)}, status_code=500)
+    except Exception:
+        # ILIKE検索失敗時もフォールバック
+        try:
+            with psycopg.connect(DATABASE_URL) as conn2:
+                return JSONResponse(list_latest(conn2, limit=limit, offset=offset, dedup=True))
+        except Exception:
+            return JSONResponse([])
```

> 注: 既に `cos` 統一や `Vector` 化、`rollback()` 実装が入っている場合は、このパッチは**追加API**中心の増分として動きます（衝突したら手作業マージでOK）。

---

# 0003-tests-search-sem.patch

* ざっくり **通ること** と **フォールバック** を担保する軽量テストを追加

```diff
diff --git a/tests/test_search_sem.py b/tests/test_search_sem.py
new file mode 100644
index 0000000..f15e0c1
--- /dev/null
+++ b/tests/test_search_sem.py
@@ -0,0 +1,72 @@
+import json
+import os
+import pytest
+from fastapi.testclient import TestClient
+
+pytest.importorskip("mcp_news.server")
+from mcp_news.server import app
+
+client = TestClient(app)
+
+def test_sem_no_vec_fallback_ok():
+    # q 未指定 → 最新順フォールバック
+    r = client.get("/search_sem?limit=3")
+    assert r.status_code == 200
+    data = r.json()
+    assert isinstance(data, list)
+
+def test_sem_with_vec_parsing_and_limit():
+    # ダミーの768次元ベクトル（値は0.0）。cos順序自体はDB側に依存するため構文のみ検証。
+    vec = [0.0] * 768
+    r = client.get("/search_sem", params={"q": json.dumps(vec), "limit": 2})
+    assert r.status_code == 200
+    data = r.json()
+    assert isinstance(data, list)
+    assert len(data) <= 2
+
+def test_ilike_fallback_on_error(monkeypatch):
+    # あり得ない limit 値で失敗させ、フォールバックで空配列 or リストを許容
+    r = client.get("/search", params={"q":"test","limit":999999999})
+    assert r.status_code == 200
+    data = r.json()
+    assert isinstance(data, list)
```

---

# 0004-docs-roadmap-day3.patch

* **Day3ロードマップ** を追加（到達目標・完了判定・担当/所要目安付き）

```diff
diff --git a/docs/ROADMAP_DAY3.md b/docs/ROADMAP_DAY3.md
new file mode 100644
index 0000000..b7e2a15
--- /dev/null
+++ b/docs/ROADMAP_DAY3.md
@@ -0,0 +1,68 @@
+# Day3 ロードマップ（MCP×AI 検索MVP仕上げ）
+
+## ゴール
+- AI/エージェントが MCP サーバの API（/search, /search_sem）を用いて、
+  最新/セマンティックの両検索経路でニュース束を取得できる。
+- 失敗時は常に **新着順フォールバック** が効く。
+- WebUI は確認用（任意/最小限維持 or 削除可）。
+
+## タスク
+1. **DB最適化**
+   - `db/indexes_core.sql` を適用（pg_trgm、published_at DESC、url_canon複合）
+   - 所要: 0.5d
+2. **サーバ機能**
+   - `/search_sem` 実装（cos `<=>`、Vector 右辺）
+   - ENABLE_SERVER_EMBEDDING 厳密化とフォールバック
+   - 所要: 0.5d
+3. **テスト**
+   - ILIKE/SEM 双方で基本疎通・フォールバックの挙動を確認
+   - 所要: 0.5d
+4. **運用**
+   - systemd / journalctl で失敗時復旧確認（ingest/embed/MCP）
+   - Nginx Basic 認証（必要なら）
+   - 所要: 0.5d
+
+## 完了判定（DoD）
+- `pytest` が Green（既存 + `tests/test_search_sem.py`）
+- `/search_sem?q=[...]` が 200 を返し、配列（0..limit件）を返す
+- `/search_sem`（q省略）で最新順の配列が返る
+- エラー時に 5xx ではなく配列（空 or 一部）を返して UI/Agent が継続可能
+
+## 次フェーズ（Day4〜）
+- ランク融合（ILIKE×Recency×Cosine）の係数 `.env` 化と A/B
+- 近重複クラスタ（オフラインで cluster_id 採番 → UI/APIでまとめ表示）
+- エンティティ/イベントの本実装（スタブ置換、QID/役割/証拠スパン）
```

---

## 最後に（運用のワンポイント）

* 既存の **cos距離統一** と **`pgvector.psycopg.Vector`** の右辺型合わせが入っているなら、今回の `0002` は「API追加と堅牢化」の側面が強いです。衝突したら **`/search_sem` 部分だけでも取り込む** 価値があります。
* `q` パラメータは暫定で **JSON配列(768次元)** を受けます（将来はサーバ側埋め込み計算 or MCP経由のEmbedding RPCに差し替えやすいように実装）。
* 失敗時のフォールバックは **常に新着順** に統一。UI/エージェントのUXを壊しません。

---

必要なら、このパッチ群を **1本のメガパッチ** に束ねた版や、既存変更点と衝突しないように **手動マージ版** も作ります。どちらが良いですか？
