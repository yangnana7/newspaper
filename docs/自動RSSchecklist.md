MCP-First 日次運用チェックリスト（newspaper）

目的
- RSS 自動巡回・埋め込み生成・API 提供の健全性を短時間で点検するための最小チェック。
- MCP-First 準拠（DB=“newshub”、API=127.0.0.1:3011、UI既定無効）。

毎日（所要3–5分）
- タイマー稼働確認:
  - `systemctl list-timers --all | egrep 'ingest|embed|events_ingest|linking|newsapi|hn'`
- 直近ジョブログ（異常有無）:
  - `journalctl -u ingest.service -n 50 --no-pager`
  - `journalctl -u embed.service  -n 50 --no-pager`
  - `journalctl -u mcp-news.service -n 50 --no-pager`
- API 待受＋MCP-First 確認:
  - LISTEN: `ss -ltnp | egrep ':3011\s'`
  - 404（UI無効）: `curl -i http://127.0.0.1:3011/ | head -n1`（HTTP/1.1 404 を期待）
  - 検索疎通: `curl -sS 'http://127.0.0.1:3011/search?q=NHK&limit=3' | jq length`
- DB の健全性/新着:
  - 総数: `psql "$DATABASE_URL" -Atc "SELECT count(*) FROM doc;"`
  - 直近24h: `psql "$DATABASE_URL" -Atc "SELECT to_char((first_seen_at AT TIME ZONE 'Asia/Tokyo')::timestamp,'YYYY-MM-DD HH24:00'),count(*) FROM doc WHERE first_seen_at > now()-interval '24 hours' GROUP BY 1 ORDER BY 1;"`
  - 埋め込みバックログ（e5-multilingual）:
    - `psql "$DATABASE_URL" -Atc "SELECT count(*) FROM chunk c LEFT JOIN chunk_vec v ON v.chunk_id=c.chunk_id AND v.embedding_space='e5-multilingual' WHERE v.chunk_id IS NULL;"`

変更のたびに（設定やユニットを触ったら）
- 固定値の遵守（MCP-First）:
  - `/etc/default/mcp-news` に以下が厳守されていること
    - `DATABASE_URL=postgresql://...@127.0.0.1:5432/newshub`
    - `APP_BIND_HOST=127.0.0.1`
    - `APP_BIND_PORT=3011`
    - `EMBEDDING_SPACE=e5-multilingual` / `EMBED_SPACE=e5-multilingual`
- 反映・再起動:
  - `sudo systemctl daemon-reload`
  - `sudo systemctl restart mcp-news.service ingest.service embed.service || true`

毎週（任意の整備）
- インデックス/拡張の健全化（安全再適用）:
  - `psql "$DATABASE_URL" -f db/indexes_core.sql`
  - `python scripts/db_ensure_indexes.py`（.venv 有効化の上で）
- ディスク/メモリ監視:
  - `df -h` / `free -h` / `top`（高負荷時はタイミング調整）

インシデント時（よくある復旧パターン）
- API が failed のまま:
  - `sudo systemctl reset-failed mcp-news.service && sudo systemctl restart mcp-news.service`
  - `journalctl -u mcp-news.service -n 100 --no-pager` で原因特定
- DB 認証エラー（fe_sendauth/password failed）:
  - `newshub_app` のパスワードと `/etc/default/mcp-news` の `DATABASE_URL` を一致させる
  - 必要に応じ `ALTER ROLE newshub_app WITH LOGIN PASSWORD '...';`
- 埋め込み未設定（EMBED_SPACE 未定義）:
  - `/etc/default/mcp-news` に `EMBED_SPACE=e5-multilingual` を追記 → `sudo systemctl restart embed.service`
- 実パス不整合（ExecStart/WorkingDirectory）:
  - ユニット内パスを実配置に合わせて修正 → `daemon-reload` → 再起動

参考
- 詳細ログ/経緯: `docs/log.md`
- 最新レポート（所見・次アクション）: `docs/report.md`
- 手順詳細（初期化〜Nginx）: `docs/runbook.md`

