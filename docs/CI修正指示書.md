（前提：本プロジェクトの固定ルールは `DB名=newshub`、`APP_BIND_HOST=127.0.0.1 / APP_BIND_PORT=3011`、UIは既定で無効です。これらはマニュアルの規約に一致させます。）

---

# 修正指示書

**対象ブランチ**: `Feature/0824 workbanch`（PR #15）
**目的**: CI 失敗の解消とメトリクス系テストの安定化。既存の非同期メトリクス・共通メトリクス実装を壊さず、MCP-First の固定環境ガードに準拠したまま通す。

## 0) 作業全体方針

* **環境固定は緩めない**（`newshub`/`127.0.0.1:3011`）。CI 環境に**正しい環境変数を注入**して通す。
* **DB接続を import 時に行わない**（モジュール import だけで失敗しないように遅延接続に統一）。
* メトリクスの pytest は **`prometheus_client` をインストールして実行**（未導入時に skip するロジックは残しつつ、CI では走らせる）。

---

## 1) 失敗再現と現状把握（自動）

**端末コマンド（そのまま実行）**

```bash
git fetch origin
git checkout Feature/0824\ workbanch
git pull
python -m venv .venv && source .venv/bin/activate
python -VV
pip install -U pip
# まず最小依存で失敗ログを得る
pip install -r requirements.txt || true
pytest -q || true
```

> ここで出る典型的失敗：
>
> * `ModuleNotFoundError: prometheus_client`（メトリクス系テスト）
> * `require_fixed_env()` での強制終了（環境変数未設定）

---

## 2) テスト用デフォルト環境の注入（import失敗の解消）

**ファイル追加**: `tests/conftest.py`（新規）

```python
# tests/conftest.py
import os

# CI/ローカルで未設定でも import できるように最低限を固定
os.environ.setdefault("DATABASE_URL", "postgresql://127.0.0.1/newshub")
os.environ.setdefault("APP_BIND_HOST", "127.0.0.1")
os.environ.setdefault("APP_BIND_PORT", "3011")
os.environ.setdefault("CI", "true")
```

* これで `mcp_news.server` import 時の**環境ガード**は満たせる（固定値に合致）。

> **注意**：ここでは DB に接続しない前提（= サーバ側は「import だけでは DB 接続しない」設計に揃える）。もし import 時に DB 接続が走る実装が残っていたら、**接続初期化をアプリ起動時（関数呼出し時）へ遅延**するよう微修正すること。

---

## 3) 依存の明示（CIでメトリクス系テストを確実に実行）

**修正**: `requirements-dev.txt`（新規 or 追記）、`requirements.txt` は変更せず可

```text
# requirements-dev.txt
pytest>=8.2
pytest-asyncio>=0.23
prometheus_client>=0.20
httpx>=0.27
fastapi>=0.111
uvicorn>=0.30
```

> メトリクス系は **prometheus\_client** を CI で必ず入れる。未導入時 skip の分岐はテストに残してOK。

---

## 4) GitHub Actions の修正（環境変数＋dev 依存の導入）

**修正**: `.github/workflows/ci.yml`

* Python 3.11 を明示
* env に**固定値**を注入（DB 実接続は不要。import ガード通過のみが狙い）
* dev 依存をインストールしてから pytest 実行

**差分案（主要部）**：

```yaml
name: CI

on:
  push:
    branches: [ "Feature/0824 workbanch", "master" ]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    env:
      PYTHONUNBUFFERED: "1"
      PIP_DISABLE_PIP_VERSION_CHECK: "1"
      DATABASE_URL: postgresql://127.0.0.1/newshub
      APP_BIND_HOST: 127.0.0.1
      APP_BIND_PORT: "3011"
      CI: "true"  # pytest 等で参照されることがある

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install -U pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi

      - name: Run tests
        run: pytest -q
```

> ポイント：**PostgreSQL のサービスは起動しない**（pgvector 拡張が必要になるため）。テストは**接続不要パス**で通る構成に徹する。DB が必要な統合試験は別ワークフローに分離する方針。

---

## 5) server import 時の副作用排除（必要な場合のみ）

もし `mcp_news/server.py` で**モジュール import 直後に DB 接続**をしている場合、**遅延初期化**へ変更する。

**修正指針**（例）：

```python
# mcp_news/server.py（例示）
from mcp_news.config_guard import require_fixed_env
require_fixed_env()  # ← これは残す（環境固定のガード）:contentReference[oaicite:5]{index=5}

# BAD: ここで psycopg.connect() などを実行しない
# DB接続はエンドポイント関数や startup イベントで実施する
# FastAPI なら @app.on_event("startup") / lifespan 内で初期化
```

* **環境ガードは必須**（固定ルール順守）。DB の**実接続だけを遅延**させる。

---

## 6) メトリクス系テストの安定化（軽微調整）

* 非同期デコレータの計測は**イベントループ 1 tick**待つと安定する場合がある。テスト内で `await asyncio.sleep(0)` を1回入れる（必要時のみ差し込み）。
* すでに `prometheus_client` 未導入時に `pytest.skip` の分岐があるため、CI では dev 依存を入れるだけで**必ず実行**される。

---

## 7) 実行・検証（ローカル→CI）

**端末コマンド**

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

* 期待：`tests/test_metrics_counters.py`, `test_metrics_async.py`, `test_metrics_integration.py`, `test_ci_env.py` が**全件成功**。
* 成功後、PR #15 に push（同ブランチ）。

---

## 8) 出力物

* 変更ファイル：

  * `tests/conftest.py`（新規）
  * `requirements-dev.txt`（新規 or 追記）
  * `.github/workflows/ci.yml`（修正）
  * （必要時）`mcp_news/server.py` の**遅延初期化**リファクタ（import 時のDB接続排除）
* コミット例：

  * `ci: inject fixed env & dev deps; ensure metrics tests run`
  * `test: add conftest to satisfy env guard on import`
  * `refactor(server): delay DB init to startup (no import-time connect)`

---

## 9) 受け入れ基準（Definition of Done）

* GitHub Actions の CI が**緑**（全ジョブ成功）
* ローカル `pytest -q` でも**0 失敗**
* 環境固定ルール（`newshub`, `127.0.0.1:3011`）は**維持**されている（env 経由・テストで担保）。
* 既存メトリクス（`items_ingested_total`, `embeddings_built_total`, `ingest_duration_seconds_count`, `embed_duration_seconds_count`）の\*\*+1 以上の増分がテストで確認\*\*できる（今回の追加テスト要件）。
* 人手レビュー観点：**import 時副作用なし**、UIは既定で無効（MCP-First）。

---

## 10) 補足（今後の分離）

* 将来、**DB を伴う統合試験**は `ci-db.yml`（別ワークフロー）で Postgres 16 + `pgvector` イメージを使い実行。現行 CI は**ユニット中心**で高速化する。
* マニュアル／設計書は**不変**（更新対象外）。参照のみ。
