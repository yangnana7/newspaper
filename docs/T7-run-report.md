# T7 実施状況 調査報告書（Codex CLI）

- 日時: 2025-08-31
- 対象リポジトリ: `newspaper`（/home/yang_server/newspaper）
- 実施者: Codex CLI
- 参考資料: docs/T7CodexCLI2.md, README.md, docs/log.md, deploy/*, mcp_news/*, web/*, db/*

## サマリ（結論）

- 停滞ポイントは「docs/T7CodexCLI2.md で定義した最終手順（journalctl/systemctl/psql による収集と受け入れレポート作成）」の実行段で停止。
- 主な技術的要因は以下の不整合と外部依存（systemd/DB）:
  - サービス起動対象の不一致: `uvicorn mcp_news.server:app` 指示と、実コード上の HTTP アプリ実体は `web.app:app` の乖離。
  - `require_fixed_env()` による環境ガード（`EMBEDDING_SPACE/EMBED_SPACE` 必須）での起動失敗が混在（docs/log.md にて EMBED_SPACE 追加で解消済みの形跡）。
  - systemd/journalctl/psql などサーバ外部環境に依存する検証・ログ収集が Codex 実行環境（ワークスペース内）では直接実行できず停止した。
- 受け入れ観点はコード静的確認で多くが満たされるが、実機確認が必要な項目（timer 状態、DBレコード件数、journalctl ログ）は未収集。

## 何がどこで詰まったか

- docs/T7CodexCLI2.md は以下の成果物を「Codexに必ず生成させる」と明記:
  - 実行ログ: `/opt/mcp-news/logs/T7-postfix.log`, `/opt/mcp-news/logs/T7-journey.log`
  - 受入チェック要約: `docs/T7-run-report.md`
- しかし、これらは systemd/journalctl/DB へアクセスする必要があり、Codex のワークスペース権限では直接取得不可。
- さらに、mcp-news.service の ExecStart 指示がコード実態と齟齬:
  - 指示書: `ExecStart=/opt/mcp-news/.venv/bin/uvicorn mcp_news.server:app ...`
  - 実コード:
    - HTTP API は `web/app.py` の `app`（FastAPI）。
    - `mcp_news/server.py` は MCP stdio サーバ（`FastMCP`）であり ASGI の `app` を公開していない。
  - 症状（docs/log.md）: `systemctl is-active mcp-news.service` は failed だが、`ss -ltnp` 上は `uvicorn` が 127.0.0.1:3011 LISTEN。
    - すなわち unit の状態と実プロセスが乖離（手動起動、または ExecStart ミスマッチによる失敗→別経路で起動）。

## 確認したサーバ設定・コード状況

- 環境ガード: `mcp_news/config_guard.py`
  - DB名 `newshub` 固定、`APP_BIND_HOST/PORT=127.0.0.1:3011` 固定、`EMBEDDING_SPACE/EMBED_SPACE` 必須を強制。
- HTTP API 実体: `web/app.py`
  - 既定 UI 無効（`/` は UI_ENABLED 未設定で 404）。
  - 公開 API: `/search`, `/search_sem`, `/api/*`, `/metrics` 等。
- MCP サーバ: `mcp_news/server.py`
  - MCP tools（検索・エンティティ・イベント等）を stdio で提供。ASGI `app` ではない。
- デプロイ定義:
  - `deploy/mcp-news.service`: `ExecStart=/opt/mcp-news/.venv/bin/python -m mcp_news.server`（stdio 起動）
  - docs/T7CodexCLI{,2}.md: `uvicorn mcp_news.server:app` 指示（HTTP 前提）
  - 正: HTTP を出すなら `uvicorn web.app:app --host 127.0.0.1 --port 3011`（README.md に準拠）
- DB/ベクトル: `db/schema_v2.sql` には `vector_l2_ops` と `vector_cosine_ops` の両方の HNSW 定義あり
  - 運用方針は cos 固定。L2 の残骸は不要（T7 指示書も警告）。
  - `db/indexes_core.sql`/`db/index_hnsw_chunk_vec.sql` は cosine で統一済み。

## 受け入れ観点の現状（静的確認ベース）

- MCP-First 準拠: OK（web/app.py の `/` は UI_DISABLED→404）。
- 不変条件:
  - DB 名 newshub 固定: OK（config_guard）。
  - バインド 127.0.0.1:3011 固定: OK（config_guard）。
  - ベクトル次元 768 / 距離 cos: 実装・クエリは cos `<=>` を使用。DDL には L2 残骸あり（後述）。
- pgvector/HNSW:
  - クエリは `<=>` を使用（cosine）。
  - HNSW は `indexes_core.sql`/`index_hnsw_chunk_vec.sql` で cosine 指定。
  - `schema_v2.sql` の L2 インデックス行は削除/無効化を推奨。
- タイマー・ジョブ: deploy/ に timer/service 定義あり。実稼働状態は未確認（外部環境依存）。
- 取り込み件数・最新時刻: 未確認（外部 DB 依存）。
- 既知エラー再発（CHDIR/203/EXEC）: docs/T7CodexCLI2.md が指摘。WorkingDirectory/ExecStart の正規化で解消見込み。

## 想定される根本原因と対処案

1) mcp-news.service の ExecStart ミスマッチ
- 原因: `mcp_news.server:app` は実在しない ASGI。HTTP は `web.app:app`。
- 対処: HTTP 公開を行う unit は以下いずれかで一本化。
  - HTTP API: `ExecStart=.../uvicorn web.app:app --host ${APP_BIND_HOST} --port ${APP_BIND_PORT}`
  - MCP stdio: `ExecStart=.../python -m mcp_news.server`（HTTP ではない）
- 受け入れで `GET /search` を確認するなら前者（web.app）を採用。

2) EMBED_SPACE/EMBEDDING_SPACE 未設定
- 原因: `require_fixed_env()` で致命。docs/log.md に「EMBED_SPACE を /etc/default/mcp-news に追記」記録あり。
- 対処: `/etc/default/mcp-news` に `EMBEDDING_SPACE` と `EMBED_SPACE` を同値で明示。

3) WorkingDirectory の不一致
- 原因: 指示書は `/opt/mcp-news`、実行が `/home/yang_server/newspaper` に混在すると unit やスクリプト参照が崩れる。
- 対処: いずれかに統一（推奨: `/opt/mcp-news` へ配置・権限調整）。

4) HNSW の L2 残骸
- 原因: `schema_v2.sql` に `vector_l2_ops` の古い記述が残存。
- 対処: 運用は cosine 固定。L2 行は削除、または適用しないこと（DDL 修正時は既存 idx を drop）。

## 実行できなかった項目（要サーバ権限/実機）

- `systemctl status/list-timers` によるサービス・タイマー状態取得
- `journalctl` による各ユニットの 24h/72h ログ収集
- `psql` による拡張・件数確認

上記は Codex のワークスペース権限外であり、このレポートではコード・資料の静的確認に留めました。実機での取得を希望される場合、承認付きでコマンド実行（sudo/systemd/journal/psql）を行います。

## 次アクション（提案）

- 単一ユニットの正規化（HTTP 公開）:
  - `WorkingDirectory=/opt/mcp-news`
  - `ExecStart=/opt/mcp-news/.venv/bin/uvicorn web.app:app --host ${APP_BIND_HOST} --port ${APP_BIND_PORT}`
  - `EnvironmentFile=/etc/default/mcp-news`
- EMBED スペース環境の二重化ガード: `/etc/default/mcp-news` に `EMBEDDING_SPACE` と `EMBED_SPACE` を同値で保持。
- pgvector/HNSW: L2 インデックス定義を除去（cosine のみ運用）。
- 受入ログ生成（実機）:
  - `/opt/mcp-news/logs/T7-postfix.log`（T7CodexCLI2.md のスクリプト実行結果）
  - `/opt/mcp-news/logs/T7-journey.log`（journal 抽出）
- docs/T7-run-report.md の最終更新（本ファイル）と、必要に応じて追補ログを docs/T7-run-log.md に反映。

---

この報告書は、docs/T7CodexCLI2.md の受入要件に沿って、現状のコード・設定から判明した停滞要因と是正方針を整理したものです。実機での確認・ログ採取の承認があれば、続けて収集と最終受入判定を実施します。

