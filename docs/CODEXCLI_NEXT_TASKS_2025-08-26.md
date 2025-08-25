# CodexCLI 次タスク指示書 & 達成チェックシート（2025-08-26 JST）

本書は 重複を除いた“実施すべき次作業”のみ を列挙します。直前ステージの報告／設計メモ／運用メモを突き合わせた上で再構成しました。

## 0. 直前ステージの反映（完了扱い・再提出不要）
- `web/app.py` の pgvector/fastapi/psycopg のオプション化 と README の UI_ENABLED=1 記載は完了（Start Check Sheet 報告）。
- メトリクスに entities_linked_total / events_with_participants_total を追加済み（運用メモ）。
- エンティティ／イベント系は、以下の新規スクリプトと API 拡張が実装済み：
  `scripts/ingest_entities.py`、`scripts/event_extract.py`、`scripts/ingest_events.py`、`scripts/link_entities_wikidata.py`、`mcp_news/server.py` の `event_timeline`/`entity_search` 強化。

---

## 1. 次に着手するタスク（実装オーダー）

### T1. エンティティ連携・イベント抽象の 運用統合（systemd + 設定）
目的: 既存の EL（Wikidata 連携）/イベント抽出を安全に定期実行（MCP-First を維持）。
作業:
- `config/linking.yaml` を確定（既存あり）。少なくとも `min_confidence`、`requests_per_sec`、`max_retries`、`prefer_lang`、`progress_file` を明示。
- `scripts/link_entities_wikidata.py` を 30 分間隔の `linking.timer` に登録。
- `scripts/ingest_events.py` を 30 分間隔の `events_ingest.timer` に登録（抽出は内部で `event_extract` を利用）。
- `/etc/default/mcp-news` に `LINK_PROGRESS_FILE`（または `PROGRESS_FILE`）を追記して再開可能に。

CodexCLI 指示:
```bash
# 1) 設定（既存の内容を確認し、必要なら更新）
rg -n "min_confidence|requests_per_sec|progress_file" config/linking.yaml || true

# 2) systemd units（/opt/mcp-news 運用に合わせる）
cat > deploy/linking.service <<'UNIT'
[Unit]
Description=Link entities via Wikidata (newshub)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/default/mcp-news
WorkingDirectory=/opt/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/python scripts/link_entities_wikidata.py --config config/linking.yaml
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

cat > deploy/linking.timer <<'UNIT'
[Unit]
Description=Run entity linking periodically

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
UNIT

cat > deploy/events_ingest.service <<'UNIT'
[Unit]
Description=Ingest events into newshub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/default/mcp-news
WorkingDirectory=/opt/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/python scripts/ingest_events.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

cat > deploy/events_ingest.timer <<'UNIT'
[Unit]
Description=Run events ingest periodically

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
UNIT

# 3) 導入手順（例）
echo "LINK_PROGRESS_FILE=/opt/mcp-news/tmp/linking_progress.txt" | sudo tee -a /etc/default/mcp-news
sudo cp deploy/linking.* deploy/events_ingest.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now linking.timer events_ingest.timer
systemctl list-timers | rg -n "linking|events_ingest" || true
```

補足:
- `link_entities_wikidata.py` は `config/linking.yaml` と `LINK_PROGRESS_FILE/PROGRESS_FILE` を自動読込します。
- 既存の `deploy/README.md` と整合させるため、`WorkingDirectory=/opt/mcp-news`、仮想環境は `/opt/mcp-news/.venv` を採用。

DoD: 2 つの timer が `active (waiting)`。実行後、Prometheus に `entities_linked_total` / `events_with_participants_total` の増分が観測でき、`journalctl -u linking.service`/`events_ingest.service` に成功ログが残る。

---

### T2. config_guard をコードに実装（ドキュメント→本実装）
目的: DB名 `newshub`、バインド `127.0.0.1:3011`、embedding 空間の固定を 起動時ガード で強制。
作業:
- `mcp_news/config_guard.py` を作成。
- `mcp_news/server.py` の起動前（import 直後）で `require_fixed_env()` を呼び出し。
- `tests/test_env_lock.py` は既存。必要なら `tests/test_ui_policy.py` を追加し、`/` が 404（`UI_ENABLED=1` 以外）を担保。

CodexCLI 指示:
```bash
apply <<'PY' :: mcp_news/config_guard.py
import os, sys
def _die(msg: str):
    sys.stderr.write(f"[FATAL CONFIG] {msg}\n"); sys.exit(2)
def require_fixed_env():
    url = os.environ.get("DATABASE_URL","")
    if "/newshub" not in url: _die("DATABASE_URL must point to 'newshub'")
    if os.environ.get("APP_BIND_HOST")!="127.0.0.1" or os.environ.get("APP_BIND_PORT")!="3011":
        _die("APP_BIND must be 127.0.0.1:3011")
    if not os.environ.get("EMBEDDING_SPACE") and not os.environ.get("EMBED_SPACE"):
        _die("EMBEDDING_SPACE/EMBED_SPACE must be set")
PY

edit mcp_news/server.py <<'SED'
/^from / i from mcp_news.config_guard import require_fixed_env
/^mcp = FastMCP/ i require_fixed_env()
SED
```

DoD: CI で環境逸脱時に 明示 Fail、ローカル既定設定下で全テスト通過。

---

### T3. CI をフルテスト化（PostgreSQL + pgvector 起動）
目的: `SKIP_DB_TESTS=1` を撤廃（本番相当で落ちないことを保証）。
作業:
- GitHub Actions に postgres service を追加し、`CREATE EXTENSION vector;` を実行。
- 既存ワークフローの env から `SKIP_DB_TESTS` を削除（または `0` に設定）。
- スキーマ適用（`db/schema_v2.sql` と `db/indexes_core.sql`）。
- `pytest -q` で 0 failed を保証。

CodexCLI 指示（.github/workflows/ci.yml の該当差分のみ）:
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: newshub
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_HOST_AUTH_METHOD: trust
        ports: ["5432:5432"]
        options: >-
          --health-cmd="pg_isready -U postgres" --health-interval=10s --health-timeout=5s --health-retries=5
    env:
      DATABASE_URL: postgresql://postgres:postgres@localhost:5432/newshub
      APP_BIND_HOST: 127.0.0.1
      APP_BIND_PORT: '3011'
      CI: 'true'
      # SKIP_DB_TESTS: '0'  # 削除または 0 に設定
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi
      - name: Prepare DB
        run: |
          until pg_isready -h localhost -U postgres -d newshub; do sleep 1; done
          psql postgresql://postgres:postgres@localhost:5432/newshub -c "CREATE EXTENSION IF NOT EXISTS vector;"
          psql postgresql://postgres:postgres@localhost:5432/newshub -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
          psql postgresql://postgres:postgres@localhost:5432/newshub -f db/schema_v2.sql
          psql postgresql://postgres:postgres@localhost:5432/newshub -f db/indexes_core.sql
      - name: Run tests
        run: pytest -q
      - name: Check vector index
        run: psql "$DATABASE_URL" -c "\\d+ chunk_vec" | rg -n hnsw || true
```

DoD: CI バッジ Green（DB依存テストを含む）。

---

### T4. UI マニュアル `docs/UI_MANUAL.md` の作成
目的: 最小 UI（FastAPI+HTML）の起動〜操作〜API 直叩きまでを整理。
作業:
- 起動: `UI_ENABLED=1 uvicorn web.app:app --host 127.0.0.1 --port 3011`（既定は 404: MCP-First）
- 検索: `/search`、セマンティック: `/search_sem`、イベント: `/api/events`
- Prometheus: `/metrics` の説明、推奨 curl サンプルと Grafana 取り込みリンク。

推奨追記:
- 動作確認の curl 例（JST 表示確認）
  - `curl 'http://127.0.0.1:3011/api/latest?limit=3' | jq .`
  - `curl 'http://127.0.0.1:3011/api/search?q=OpenAI&limit=5' | jq .`
  - `curl 'http://127.0.0.1:3011/metrics' | head`

DoD: 初見の利用者が 10 分で最新記事の表示／検索／イベント API の確認が可能。

---

### T5. 近重複クラスタリングの受入テスト拡充
目的: SimHash/MinHash のクラスタ精度の下限保証。
作業:
- `tests/test_near_duplicate.py` のカバレッジを増やし、タイトル改変・別ソース同記事を想定したフィクスチャを追加。
- 閾値（ハミング距離/Jaccard）を外部化（`config/ranking.yaml` もしくは新設ファイル）し、テストから読み込む。

DoD: 小規模評価セットで dup_ratio 15–35% を満たす。

---

## 2. 達成チェックシート
- [ ] linking/events 2 timer が起動し、メトリクスが増分する（entities_linked_total / events_with_participants_total）。
- [ ] config_guard 実装で、環境逸脱時にサーバ起動が Fail Fast する。
- [ ] CI（DB有）で 0 failed、`SKIP_DB_TESTS` 依存がない（スキーマ適用済み）。
- [ ] `docs/UI_MANUAL.md` に沿って、検索/UI/API/メトリクスが 手順通り 動く。
- [ ] 近重複のテストが評価セットで 基準値（dup_ratio 15–35%） を満たす。

---

## 3. 参考（根拠ファイル）
- 0826 Start Check Sheet（完了内容）
- 0826 Start Check Sheet 実施報告（pgvector等のオプション化・テスト状況）
- 2025-08-28 作業ログ（EL/イベント実装の詳細・予定）
- エンティティ／イベント設計メモ（linking.yaml の骨子ほか）
- メトリクス運用メモ（entities_linked_total などの導入）
- SSH ポートフォワード手順（MCP-First 準拠）

