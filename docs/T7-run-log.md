# T7 実施ログ（Codex CLI 調査）

- 日時: 2025-08-31
- 実施者: Codex CLI
- 目的: 「先ほどの作業がどこで詰まったか」を特定し、サーバ設定の状況・差分・阻害要因を整理する。

## 手順ログ（ワークスペース内の確認）

- リポジトリ構成確認: `ls -la`, `tree -L 2`
- docs 一覧確認: `docs/T7CodexCLI.md`, `docs/T7CodexCLI2.md`, `docs/log.md` ほか
- サーバ関連コードの読み取り:
  - ガード: `mcp_news/config_guard.py`（DB=newshub / 127.0.0.1:3011 / EMBED_SPACE 必須）
  - MCP: `mcp_news/server.py`（MCP stdio サーバ、ASGI app なし）
  - HTTP: `web/app.py`（FastAPI app 実体、`/search`, `/search_sem`, `/api/*`, `/`=UI 既定404）
- デプロイ定義の確認:
  - `deploy/mcp-news.service`（stdio 起動: `python -m mcp_news.server`）
  - docs/T7CodexCLI{,2}.md の ExecStart 指示（`uvicorn mcp_news.server:app`）との齟齬を確認
- DB スキーマ確認:
  - `db/schema_v2.sql`（HNSW に L2/CoS 両方の定義）
  - `db/indexes_core.sql`, `db/index_hnsw_chunk_vec.sql`（cosine 統一）
- 既存運用ログの参照: `docs/log.md`
  - EMBED_SPACE を `/etc/default/mcp-news` に追記→embed.service が正常化
  - `systemctl is-active mcp-news.service` は failed だが、`ss -ltnp` では `uvicorn` が 127.0.0.1:3011 LISTEN（unit と実プロセス乖離）

## 技術的着眼点（抜粋）

- HTTP API は `web.app:app` が唯一の ASGI 実体。`mcp_news.server:app` 指示は ASGI 不在で不正。
- `require_fixed_env()` により EMBED_SPACE/EMBEDDING_SPACE 未設定は致命。
- HNSW のインデックスは cosine で統一すべき（L2 残骸は適用対象外に）。
- 受入確認（UI OFFの404, /search 200）を systemd ユニット経由で行うなら、ExecStart は `uvicorn web.app:app` を用いる。

## 実行できなかった外部確認（要権限）

- `systemctl status/list-timers`（ingest/embed/newsapi/hn の稼働状態）
- `journalctl -u ...`（24h/72h ログ抜粋）
- `psql $DATABASE_URL`（拡張/件数/インデックス）

承認いただければ、これらコマンドを実サーバで実行し、`/opt/mcp-news/logs/T7-postfix.log` と `/opt/mcp-news/logs/T7-journey.log` を生成の上で本ログに追記します。

## 推奨アクション（抜粋）

- mcp-news.service（HTTP 公開ユニット）は以下で統一:
  - `WorkingDirectory=/opt/mcp-news`
  - `ExecStart=/opt/mcp-news/.venv/bin/uvicorn web.app:app --host ${APP_BIND_HOST} --port ${APP_BIND_PORT}`
  - `EnvironmentFile=/etc/default/mcp-news`
- `/etc/default/mcp-news`: `EMBEDDING_SPACE` と `EMBED_SPACE` を同値で定義（ガード回避）。
- DDL: `schema_v2.sql` の `vector_l2_ops` インデックスは削除（cosine に一本化）。
- 受入確認とログ採取を再実施（T7CodexCLI2.md の手順に準拠）。

