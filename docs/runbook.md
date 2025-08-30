MCP-First 運用 Runbook（恒久化・確認・復旧）

前提
- OS: Ubuntu Server 24.04 LTS
- DB: PostgreSQL + `pgvector` + `pg_trgm`
- ポリシー固定: DB 名は `newshub`、API は `127.0.0.1:3011`、ベクトル次元は `vector(768)`、距離は cos（`<=>`）。
- UI は既定で無効（MCP-First）。

1. データベース初期化（初回のみ）
- DB 作成と拡張:
  - `sudo -u postgres psql <<'SQL'
CREATE DATABASE newshub;
\c newshub
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL`
- 既存スキーマ適用（必要に応じて）:
  - `psql postgresql://127.0.0.1/newshub -f db/schema_v2.sql`
  - `psql postgresql://127.0.0.1/newshub -f db/indexes_core.sql`
- アプリ用ユーザ（例）:
  - `NEW_PASS=$(openssl rand -hex 16)`
  - `sudo -u postgres psql <<SQL
CREATE ROLE newshub_app LOGIN PASSWORD '${NEW_PASS}';
GRANT CONNECT ON DATABASE newshub TO newshub_app;
\c newshub
GRANT USAGE ON SCHEMA public TO newshub_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO newshub_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO newshub_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO newshub_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO newshub_app;
SQL`

2. 環境ファイル `/etc/default/mcp-news`
- 最低限（固定値を含む）:
  - `DATABASE_URL=postgresql://newshub_app:${NEW_PASS}@127.0.0.1:5432/newshub`
  - `APP_BIND_HOST=127.0.0.1`
  - `APP_BIND_PORT=3011`
  - `LOG_LEVEL=info`
  - `EMBEDDING_SPACE=e5-multilingual`
  - `EMBED_SPACE=e5-multilingual`
- 任意:
  - `ENABLE_SERVER_EMBEDDING=0`（既定: クライアント側で埋め込み）
  - `NEWSAPI_KEY=...`（NewsAPI 利用時）

3. systemd ユニット配置
- 配置:
  - `sudo cp deploy/ingest.service /etc/systemd/system/`
  - `sudo cp deploy/ingest.timer   /etc/systemd/system/`
  - `sudo cp deploy/embed.service  /etc/systemd/system/`
  - `sudo cp deploy/embed.timer    /etc/systemd/system/`
  - `sudo cp deploy/mcp-news.service /etc/systemd/system/`
  - オプション: `newsapi-tech-jp.service|timer`, `hn-top.service|timer`, `events_ingest.service|timer`, `linking.service|timer`
- 実パス調整（いずれか一方）:
  - 推奨: `/opt/mcp-news` にコードを配置し、ユニット内を `/opt/mcp-news` と `.venv` に統一。
  - もしくはリポ直下で運用: `WorkingDirectory=/home/<user>/newspaper`、`ExecStart=/home/<user>/newspaper/.venv/bin/...` に置換。
- `mcp-news.service`（例・MCP-First 構成）:
  - `WorkingDirectory=/home/<user>/newspaper`
  - `EnvironmentFile=/etc/default/mcp-news`
  - `ExecStart=/home/<user>/newspaper/.venv/bin/uvicorn mcp_news.server:app --host ${APP_BIND_HOST} --port ${APP_BIND_PORT}`

4. 有効化と起動
- `sudo systemctl daemon-reload`
- `sudo systemctl enable --now ingest.timer embed.timer events_ingest.timer`
- オプション: `sudo systemctl enable --now newsapi-tech-jp.timer hn-top.timer`
- API: `sudo systemctl enable --now mcp-news.service`

5. 初回取り込みの手動確認
- `cp -n config/feeds.sample.json config/feeds.json`
- `source .venv/bin/activate && export DATABASE_URL=postgresql://127.0.0.1/newshub`
- `python scripts/ingest_rss.py --feeds config/feeds.json`
- `psql "$DATABASE_URL" -Atc "SELECT count(*) FROM doc;"`

6. 埋め込み生成の確認
- `sudo systemctl start embed.service`
- `journalctl -u embed.service -n 50 --no-pager`
- `EMBED_SPACE` 未設定時はエラーになるため `/etc/default/mcp-news` に追記（`EMBED_SPACE=e5-multilingual`）。

7. API 動作確認（MCP-First）
- LISTEN 確認: `ss -ltnp | egrep ':3011\s'`
- `/search`: `curl -sS 'http://127.0.0.1:3011/search?q=NHK&limit=3'`
- `/search_sem`: `curl -sS 'http://127.0.0.1:3011/search_sem?q=AI&limit=3'`
- `/` は 404 が正（UI 無効）: `curl -i http://127.0.0.1:3011/`

8. ログ・監視
- 直近ログ: `journalctl -u ingest.service -n 50 --no-pager`
- タイマー一覧: `systemctl list-timers --all | egrep 'ingest|embed|events_ingest|linking|newsapi|hn'`
- DB 24h 推移: `psql "$DATABASE_URL" -Atc "SELECT to_char((first_seen_at AT TIME ZONE 'Asia/Tokyo')::timestamp,'YYYY-MM-DD HH24:00'),count(*) FROM doc WHERE first_seen_at > now() - interval '24 hours' GROUP BY 1 ORDER BY 1;"`

9. トラブルシュート
- `fe_sendauth: no password supplied` / `password authentication failed`:
  - DB ロール `newshub_app` のパスワードを再設定し、`/etc/default/mcp-news` の `DATABASE_URL` と一致させる。
- `embed.service: Referenced but unset environment variable EMBED_SPACE`:
  - `/etc/default/mcp-news` に `EMBED_SPACE=e5-multilingual` を追記。
- API が `failed` のまま:
  - `sudo systemctl reset-failed mcp-news.service && sudo systemctl restart mcp-news.service`
  - `journalctl -u mcp-news.service -n 100 --no-pager` を参照。
- `ExecStart`/`WorkingDirectory` 不整合:
  - 実パスに合わせてユニットを置換後、`daemon-reload` と再起動。

10. Nginx 連携（UI 非公開）
- 例（UI を 403、API のみ転送）:
  - `location = / { return 403; }`
  - `location /static/ { return 403; }`
  - `location /search { proxy_pass http://127.0.0.1:3011; }`
  - `location /search_sem { proxy_pass http://127.0.0.1:3011; }`
  - `location /api/ { proxy_pass http://127.0.0.1:3011; }`

11. 運用メモ
- 取り込み周期: `ingest.timer` は 10 分毎（`OnCalendar=*:0/10`）。
- 近似重複は `cluster` で束ね、埋め込み後に検索性能が安定。
- 変更時は `daemon-reload` を忘れずに。環境値変更後は該当サービスを再起動。

12. 片付け（停止/無効化）
- タイマー停止: `sudo systemctl disable --now ingest.timer embed.timer events_ingest.timer`
- API 停止: `sudo systemctl disable --now mcp-news.service`

参考
- 詳細ログは `docs/log.md`、直近のレポートは `docs/report.md` を参照。

