# 次回修正タスク一覧 (2025-08)

対象: MCPニュース集約サーバー (Ubuntu 24.04 / i3-6100T / 8GB RAM)
参照: 作業ログ報告書 (2025-08-23)

---

## 1. systemd サービス修正 (高優先度)
- **問題**: `mcp-news.service` が `mcp_news.server:app` を参照 → 実際のアプリは `web.app:app`
- **対応**:
  ```ini
  # /etc/systemd/system/mcp-news.service
  ExecStart=/opt/mcp-news/.venv/bin/uvicorn web.app:app --host ${APP_BIND_HOST} --port ${APP_BIND_PORT}
  ```
- 修正後に以下を実行:
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl restart mcp-news.service
  sudo systemctl status mcp-news.service
  ```

---

## 2. `/search` API の実装確認 (高優先度)
- **問題**: `/search` エンドポイントが 404 → 設計仕様と不一致。
- **調査手順**:
  1. `web/app.py` 内に `/search` 実装があるか確認。
  2. 実装がない場合 → `mcp_news/server.py` の検索機能を FastAPI 側に統合。
  3. `/search_sem` (ベクトル検索) も同時に確認。
- **テスト**:
  ```bash
  curl "http://127.0.0.1:3011/search?q=test"
  ```

---

## 3. 埋め込み処理設定確認 (中優先度)
- **問題**: `ENABLE_SERVER_EMBEDDING` が未確認。
- **対応**: `/etc/default/mcp-news` を確認し、以下の設定を保証する:
  ```bash
  ENABLE_SERVER_EMBEDDING=0
  ```
- サーバー側での埋め込み生成を禁止し、クライアント側で計算させる。

---

## 4. 継続監視 (低優先度)
- メモリ使用量 (`htop`, `free -h`) が 80% 未満で推移しているか。
- DB接続安定性 (`journalctl -u postgresql` にエラーが出ていないか)。
- API応答速度が劣化していないか。

---

## 優先度まとめ
1. **systemd サービス修正** (即対応)
2. **検索API実装確認** (即対応)
3. **埋め込み設定確認** (次回起動前に確認)
4. **継続監視** (日次確認)

---

## 次回作業時のゴール
- サービスが systemd 管理下で正常起動し、手動起動不要になること。
- `/search` と `/search_sem` が 200 OK を返すこと。
- `.env` 設定が適切で CPU負荷が過剰にならないこと。

