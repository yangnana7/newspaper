# T7 CodexCLI 実施（解決案 + 代行ログ）

- 日時: 2025-08-31
- 実施者: Codex CLI（sudo 許可あり）
- 目的: T7 停滞の解消（ExecStart/WorkingDirectory/環境ガード/pgvector 運用）と受入チェックの実施

## 解決方針（要点）

- HTTP 公開は FastAPI 実体 `web.app:app` を使用（MCP stdio `mcp_news.server` とは別系統）。
- 固定環境を二重に保証（/etc/default/mcp-news + config_guard）：
  - DB: `.../newshub`
  - Bind: `127.0.0.1:3011`
  - Embedding space: `EMBEDDING_SPACE` と `EMBED_SPACE` を同値（`e5-multilingual`）
- systemd を単一化：`mcp-news.service` の `ExecStart` を `uvicorn web.app:app` に統一。
- タイマーを復旧：`embed.timer` と `ingest.timer` を repo パス基準で作成・有効化。
- pgvector/HNSW は cosine のみ運用（L2 残骸があれば drop）。

## 実行ステップ

1) /etc/default/mcp-news を確認・補正（APP_BIND_HOST/PORT, EMBED*）
2) mcp-news.service を作成/更新（WorkingDirectory=/home/yang_server/newspaper, ExecStart=uvicorn web.app:app）
3) embed/ingest の service/timer を作成・有効化
4) 受入チェック（/ 404, /search 200/204, timers active）
5) DB 検証（pgvector 拡張、HNSW=cos、件数サマリ）
6) ログ収集（/opt/mcp-news/logs/T7-*.log）

以下、代行結果をこのファイルに追記します。

## 実行結果（要約）

- サービス起動: active (running)
  - Unit: `/etc/systemd/system/mcp-news.service`
  - ExecStart: `/home/yang_server/newspaper/.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 3011`
  - WorkingDirectory: `/home/yang_server/newspaper`
  - EnvironmentFile: `/etc/default/mcp-news`（DATABASE_URL=/newshub, APP_BIND_HOST=127.0.0.1, APP_BIND_PORT=3011, EMBED[D]ING_SPACE=e5-multilingual）
- HTTP 受入:
  - GET / -> 404（UI 既定OFF）
  - GET /search?q=hello -> 200（空でも200/204レンジ）
- タイマー:
  - `embed.timer` active（直近実行成功: no pending chunks）
  - `ingest.timer` active（RSS取得ログあり）
- DB 概況（psql）:
  - extensions: `vector`, `pg_trgm` 確認
  - 件数: `doc=5682, chunk=5682, chunk_vec=11090`
  - HNSW インデックス: `CREATE INDEX IF NOT EXISTS ... vector_cosine_ops` を適用試行（indexes_core.sql）したが、pg_indexes に列挙が出ないため別途ご確認ください（pgvector 0.5+ と権限要件の可能性）。
- ログ保存:
  - `/opt/mcp-news/logs/T7-postfix.log`（初回スナップショット）
  - `/opt/mcp-news/logs/T7-journey.log`（直近24hのjournal一括）
  - `/opt/mcp-news/logs/T7-postfix-2.log`（修正後の再スナップショット）

## 備考（運用ポリシー整合）

- MCP-First: 既定で `/` は 404。`/search`, `/search_sem`, `/api/*` は公開。
- 環境ガード: `require_fixed_env()` による固定値（DB=newshub / 127.0.0.1:3011 / EMBED* 必須）を満たす。
- HNSW: クエリは `<=>`（cos）。DDL の L2 残骸は未適用。HNSWが未作成の場合は `db/indexes_core.sql` を再適用、もしくは `CREATE INDEX ... vector_cosine_ops` を適用してください。
