
# CodexCLI 次タスク指示書 & 達成チェックシート（2025-08-26 JST）

本書は **重複を除いた“実施すべき次作業”のみ** を列挙します。直前ステージの報告／設計メモ／運用メモを突き合わせた上で再構成しました。

## 0. 直前ステージの反映（完了扱い・再提出不要）
- `web/app.py` の **pgvector/fastapi/psycopg のオプション化** と README の **UI_ENABLED=1** 記載は完了（Start Check Sheet 報告）。
- メトリクスに **entities_linked_total / events_with_participants_total** を追加済み（運用メモ）。
- エンティティ／イベント系は、以下の新規スクリプトと API 拡張が実装済み：  
  `scripts/ingest_entities.py`、`scripts/event_extract.py`、`scripts/ingest_events.py`、`scripts/link_entities_wikidata.py`、`mcp_news/server.py` の `event_timeline`/`entity_search` 強化。

---

## 1. 次に着手するタスク（実装オーダー）

### T1. エンティティ連携・イベント抽象の **運用統合（systemd + 設定）**
**目的**: 既に実装された EL/イベント処理をバッチ運用へ昇格。  
**作業**:
- `config/linking.yaml` を確定し、`min_confidence`、`requests_per_sec`、`max_retries`、`prefer_lang` を設定値として読み込む。
- `scripts/link_entities_wikidata.py` を **15分〜60分** 間隔の `linking.timer` に登録。
- `scripts/event_extract.py` → `event_extract.timer`、`scripts/ingest_events.py` → `events_ingest.timer` を作成。
- 進捗メモ（中断再開）用に `state/linked_entities.txt` を採用。

**CodexCLI 指示**:
```bash
# 1) 設定テンプレ生成
mkdir -p config state deploy
cat > config/linking.yaml <<'YAML'
min_confidence: 0.6
requests_per_sec: 3
max_retries: 3
prefer_lang: ja
blacklist_keywords: ["曖昧さ回避","disambiguation"]
YAML

# 2) systemd unit (linking)
cat > deploy/linking.service <<'UNIT'
[Unit]
Description=Link entities via Wikidata
After=network-online.target
[Service]
Type=simple
EnvironmentFile=/etc/default/mcp-news
WorkingDirectory=%h/mcp-news
ExecStart=%h/mcp-news/.venv/bin/python scripts/link_entities_wikidata.py --config config/linking.yaml
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

# 3) 同様に event_extract / events_ingest の *.service/*.timer を生成
```

**DoD**: 3 つの timer が `active (waiting)`、実行でメトリクス `entities_linked_total` / `events_with_participants_total` が増分。

---

### T2. **config_guard をコードに実装**（ドキュメント→本実装）
**目的**: DB名 `newshub`、バインド `127.0.0.1:3011`、embedding 空間の固定を **起動時ガード** で強制。  
**作業**:
- `mcp_news/config_guard.py` を作成。
- `mcp_news/server.py` の先頭で `require_fixed_env()` を呼び出し。
- `tests/test_env_lock.py` と `tests/test_ui_policy.py` を有効化。

**CodexCLI 指示**:
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
    if not os.environ.get("EMBEDDING_SPACE"): _die("EMBEDDING_SPACE must be set")
PY

edit mcp_news/server.py <<'SED'
/^from / i from mcp_news.config_guard import require_fixed_env
/^app\s*=\s*FastAPI/ i require_fixed_env()
SED
```

**DoD**: CI で環境逸脱時に **明示 Fail**、ローカル既定設定下で全テスト通過。

---

### T3. **CI をフルテスト化**（PostgreSQL + pgvector を起動）
**目的**: `SKIP_DB_TESTS=1` を撤廃（本番相当で落ちないことを保証）。  
**作業**:
- GitHub Actions に **postgres service** を追加し、`CREATE EXTENSION vector;` を実行。
- 既存ワークフローの `pip install` に `psycopg[binary] pgvector` を追加。
- `pytest -q` で **0 failed** を保証。

**CodexCLI 指示**（.github/workflows/ci.yml の該当差分のみ）:
```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_DB: newshub
      POSTGRES_HOST_AUTH_METHOD: trust
    ports: ["5432:5432"]
    options: >-
      --health-cmd="pg_isready -U postgres" --health-interval=10s
steps:
  - run: |
      psql -h localhost -U postgres -d newshub -c "CREATE EXTENSION IF NOT EXISTS vector;"
  - run: pip install "psycopg[binary]" pgvector
  - run: pytest -q
```

**DoD**: CI バッジ **Green**（DB依存テストを含む）。

---

### T4. **UI マニュアル `docs/UI_MANUAL.md` の作成**
**目的**: 最小 UI（FastAPI+HTML）の起動〜操作〜API 直叩きまでを整理。  
**作業**:
- 起動: `UI_ENABLED=1 uvicorn web.app:app --host 127.0.0.1 --port 3011`
- 検索: `/search`、セマンティック: `/search_sem`、イベント: `/api/events`
- Prometheus: `/metrics` の説明、推奨 curl サンプルと Grafana 取り込みリンク。

**DoD**: 初見の利用者が 10 分で最新記事の表示／検索／イベント API の確認が可能。

---

### T5. **近重複クラスタリングの受入テスト拡充**
**目的**: SimHash/MinHash のクラスタ精度の下限保証。  
**作業**:
- `tests/test_near_duplicate.py` のカバレッジを増やし、タイトル改変・別ソース同記事を想定したフィクスチャを追加。
- ハミング距離や Jaccard 閾値を外部化（config）。

**DoD**: 小規模評価セットで **dup_ratio 15–35%** を満たす。

---

## 2. 達成チェックシート
- [ ] linking/event 3 timer が起動し、メトリクスが増分する（entities_linked_total / events_with_participants_total）。
- [ ] config_guard 実装で、環境逸脱時にサーバ起動が **Fail Fast** する。
- [ ] CI（DB有）で **0 failed**、`SKIP_DB_TESTS` 依存がない。
- [ ] `docs/UI_MANUAL.md` に沿って、検索/UI/API/メトリクスが **手順通り** 動く。
- [ ] 近重複のテストが評価セットで **基準値（dup_ratio 15–35%）** を満たす。

---

## 3. 参考（根拠ファイル）
- 0826 Start Check Sheet（完了内容）
- 0826 Start Check Sheet 実施報告（pgvector等のオプション化・テスト状況）
- 2025-08-28 作業ログ（EL/イベント実装の詳細）
- エンティティ／イベント設計メモ（linking.yaml の骨子ほか）
- メトリクス運用メモ（entities_linked_total などの導入）
- SSH ポートフォワード手順（MCP-First 準拠）
