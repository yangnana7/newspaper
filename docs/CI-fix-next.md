CI失敗の“正体”は2点でした。
(1) **asyncデコレータが `Histogram._timer` に依存** → `prometheus_client` にはそのプライベート属性がありません（公式APIは `.time()` か自前で経過時間計測して `.observe()`）。
(2) **DBなしCIで `/api/search` テストが実DBへ接続** → `Connection refused`（CIではPostgresを立てていないため）。

下に**そのまま貼って実行できる正式な修正指示書**＋**最小チェックリスト**を出します。最後にローカルの PEP 668（externally-managed）対処も載せました。

---

# CodexCLI 修正指示書（正式版 / PR #15 対応）

**対象ブランチ:** `Feature/0824 workbanch`
**目的:** CI 赤の解消（メトリクスasync修正 / DB依存テストのスキップ制御）

## 1) asyncメトリクス計測を公称APIに修正

**修正ファイル:** `mcp_news/metrics.py`
**内容:** 非同期デコレータは `_timer` を使わず、`time.perf_counter()` で経過時間を測り `Histogram.observe()` する方式へ。

```diff
*** Begin Patch
*** Update File: mcp_news/metrics.py
@@
-from prometheus_client import Counter, Histogram, generate_latest
+from prometheus_client import Counter, Histogram, generate_latest
 import functools
 import time
@@
-# Async wrappers (use private _timer() previously)  ← ← ここが問題
-def time_ingest_operation_async(func):
-    @functools.wraps(func)
-    async def wrapper(*args, **kwargs):
-        # was: with INGEST_DURATION._timer(): await func(...)
-        # but _timer is a private API and may not exist → AttributeError
-        t0 = time.perf_counter()
-        try:
-            return await func(*args, **kwargs)
-        finally:
-            dt = time.perf_counter() - t0
-            INGEST_DURATION.observe(dt)
-    return wrapper
+def time_ingest_operation_async(func):
+    """
+    Async timing decorator using public API:
+    - start = perf_counter()
+    - await func(...)
+    - histogram.observe(elapsed)
+    """
+    @functools.wraps(func)
+    async def wrapper(*args, **kwargs):
+        t0 = time.perf_counter()
+        try:
+            return await func(*args, **kwargs)
+        finally:
+            INGEST_DURATION.observe(time.perf_counter() - t0)
+    return wrapper
 
 
-def time_embed_operation_async(func):
-    @functools.wraps(func)
-    async def wrapper(*args, **kwargs):
-        t0 = time.perf_counter()
-        try:
-            return await func(*args, **kwargs)
-        finally:
-            dt = time.perf_counter() - t0
-            EMBED_DURATION.observe(dt)
-    return wrapper
+def time_embed_operation_async(func):
+    @functools.wraps(func)
+    async def wrapper(*args, **kwargs):
+        t0 = time.perf_counter()
+        try:
+            return await func(*args, **kwargs)
+        finally:
+            EMBED_DURATION.observe(time.perf_counter() - t0)
+    return wrapper
*** End Patch
```

> 補足：同期用の `.time()` コンテキストを使う案もありますが、asyncは自前で測るのが確実です。

---

## 2) DBなしCIで `/api/search` テストをスキップ可能化

**修正方針:** DB依存の統合テストは **環境変数でスキップ**（CIではDBを立てない運用）。
**実装:**

**修正ファイル:** `tests/test_search_sem.py`（または該当するDB接続前に動くテストファイル）

```diff
*** Begin Patch
*** Update File: tests/test_search_sem.py
@@
+import os
+import pytest
+
+# CI はDBを起動しない方針。環境変数でDB依存テストを明示スキップ。
+pytestmark = pytest.mark.skipif(
+    os.getenv("SKIP_DB_TESTS") == "1",
+    reason="CI environment without database"
+)
*** End Patch
```

**修正ファイル:** `.github/workflows/ci.yml`（env にスキップフラグを追加）

```diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@
   env:
     PYTHONUNBUFFERED: "1"
     PIP_DISABLE_PIP_VERSION_CHECK: "1"
     DATABASE_URL: postgresql://127.0.0.1/newshub
     APP_BIND_HOST: 127.0.0.1
     APP_BIND_PORT: "3011"
     CI: "true"
+    SKIP_DB_TESTS: "1"
*** End Patch
```

> 将来DB統合試験を回したいときは、別のワークフロー（pgvector入りPostgresをservicesで起動）で `SKIP_DB_TESTS=0` にしてください。

---

## 3) 実行コマンド（ローカル・CI共通）

```bash
# ブランチ
git checkout "Feature/0824 workbanch"
git pull

# venv（PEP 668回避）
python3 -m venv .venv && source .venv/bin/activate

# 依存
python -m pip install -U pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# テスト
pytest -q
```

> **ローカルのエラー** `externally-managed-environment` は **venv未使用**が原因。上記の通り `python3 -m venv .venv` で解決します。

---

## 4) 受け入れ基準（DoD）

* `tests/test_metrics_async.py` と `tests/test_metrics_counters.py` が **0 failed**
  （`Histogram` の `_timer` 不要、`*_seconds_count` 増分もOK）
* `tests/test_search_sem.py` は **CIではskip**（DBなしのため）
* GitHub Actions が **成功（緑）**
* 既存の固定ルール（DB名 `newshub`、`127.0.0.1:3011`、UI既定無効）は**維持**

---

## 5) 追記（任意の改善）

* `scripts/entity_link_stub.py` が import 時に `psycopg` を要求するなら、

  * `try: import psycopg; except ImportError: psycopg = None` とし、
  * DBを使う関数内で `if psycopg is None: raise RuntimeError(...)` のように遅延判定に変更すると、**テスト収集時のImportError**を回避できます（CIでは requirements-dev で `psycopg[binary]` を入れているため実害は無いですが、ローカル互換性が上がります）。

---

# 最小チェックリスト

| No | チェック        | コマンド                                                                        | 期待                 |      |
| -- | ----------- | --------------------------------------------------------------------------- | ------------------ | ---- |
| 1  | async装飾修正適用 | `grep -n 'observe(time\\.perf_counter' mcp_news/metrics.py`                 | 2箇所ヒット             |      |
| 2  | DBスキップ導入    | `grep -n 'SKIP_DB_TESTS' tests/test_search_sem.py .github/workflows/ci.yml` | 両方ヒット              |      |
| 3  | venv使用      | `python -c "import sys;print(sys.prefix)"`                                  | `<repo>/.venv`     |      |
| 4  | 依存導入        | \`pip show prometheus-client                                                | head -n1\`         | 名前表示 |
| 5  | テスト         | `pytest -q`                                                                 | 0 failed / 一部 skip |      |

---

必要ならこのままPRにコミットメッセージ例：

```
fix(metrics): async timing uses observe(perf_counter) instead of private _timer
test: skip DB-bound search tests in CI via SKIP_DB_TESTS=1
ci: inject SKIP_DB_TESTS=1; keep fixed env; run unit tests green
```
