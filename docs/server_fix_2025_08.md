# サーバー改善アクションリスト (2025-08)

対象環境: Ubuntu 24.04 / Intel i3-6100T / 8GB RAM  
プロジェクト: MCPニュース集約サーバー  

---

## 1. 問題点
1. **systemd サービスのパス不整合**
   - `mcp-news.service` が `/root/mcp-news/` を参照しており、実際の配置 `/opt/mcp-news` と不一致。
   - 結果、`Exec error 203` で起動失敗。

2. **DB接続設定の不一致**
   - サービス定義が `postgresql://localhost/newshub` を使用。
   - 実際は認証情報付き接続が必要 (`postgresql://user:pass@localhost/newshub`)。

3. **埋め込み処理の設定誤り**
   - 現在 `ENABLE_SERVER_EMBEDDING=1`。
   - 8GB 環境では CPU 負荷過多 → `0` にする必要あり。

4. **サービス連鎖エラー**
   - `mcp-news.service` 停止により `ingest.service` / `embed.service` も失敗ループ。

---

## 2. 改善アクション

### A. アプリ配置修正
- **標準ディレクトリに統一**: `/opt/mcp-news`
- systemd サービス設定の `WorkingDirectory` と `ExecStart` を以下のように修正:
  ```ini
  WorkingDirectory=/opt/mcp-news
  ExecStart=/opt/mcp-news/.venv/bin/uvicorn mcp_news.server:app --host ${APP_BIND_HOST} --port ${APP_BIND_PORT}
  ```

### B. DB接続情報修正
- `/etc/default/mcp-news` を編集:
  ```bash
  DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/newshub
  ```
  ※ `<user>`, `<password>` は実際の DB 認証情報に置換。

### C. 埋め込み処理の無効化
- `/etc/default/mcp-news` を修正:
  ```bash
  ENABLE_SERVER_EMBEDDING=0
  ```
  - サーバー側での埋め込み生成を禁止 → クライアント側で計算する。

### D. サービス再起動
```bash
sudo systemctl daemon-reload
sudo systemctl restart mcp-news.service ingest.timer embed.timer
sudo systemctl status mcp-news.service
```

---

## 3. 確認手順
1. `systemctl status mcp-news.service` が **active (running)** になっているか確認。
2. `journalctl -u mcp-news.service -n 50` でエラーログがないか確認。
3. `curl http://127.0.0.1:3011/search?q=test` が成功するか確認。

---

## 4. 評価
- **リソース面**: CPU/メモリともに十分余裕あり。
- **最大の問題は設定ミス** → 修正すれば安定稼働可能。

