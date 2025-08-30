MCP-First 新聞基盤 デプロイ/運用レポート（2025-08-29 JST）

概要
- 目的: RSS 自動巡回＋埋め込み生成＋API サービスの恒久化および稼働確認。
- ポリシー: DB 名は `newshub` 固定、API バインドは `127.0.0.1:3011` 固定（MCP-First）。UI は既定で無効。

実施内容（要約）
- systemd timer/service 配置・有効化の確認と是正。
- DB 接続エラー（パスワード未設定）を解消: アプリ用ロール `newshub_app` を作成し、`/etc/default/mcp-news` の `DATABASE_URL` と整合。
- `embed.service` の `EMBED_SPACE` 未設定を修正（`/etc/default/mcp-news` に `EMBED_SPACE=e5-multilingual` 追加）。
- `mcp-news.service` を MCP-First 構成に統一（`EnvironmentFile` 利用、`uvicorn` で `127.0.0.1:3011` 待受）。
- `config/feeds.json` を整備し、手動 ingest により取り込みを確認。

稼働状況（確認時点）
- タイマー: `ingest.timer`（10分毎）、`embed.timer`、`events_ingest.timer` が稼働。`systemctl list-timers` で確認済み。
- Ingest: 重複を除外した取り込みが定期実行。重複は `ON CONFLICT (url) DO NOTHING` でスキップ。
- Embed: ログ上、`space=e5-multilingual, dim=768` で大量挿入後「no pending chunks」を確認。
- API: `uvicorn` が `127.0.0.1:3011` で LISTEN。MCP-First により `/` は 404、`/search`・`/search_sem` は応答。

DB スナップショット（参考）
- doc 総数: 5401
- 直近24hの挿入（JSTバケット例）: `2025-08-29 06:00 | 117`
  - 注: 値は時点の一例。最新は下記のコマンドで再確認。

確認コマンド（抜粋）
- タイマー: `systemctl list-timers --all | egrep 'ingest|embed|events_ingest|linking|newsapi|hn'`
- API LISTEN: `ss -ltnp | egrep ':3011\s'`
- API 疎通: `curl -sS 'http://127.0.0.1:3011/search?q=NHK&limit=3'`
- UI 無効: `curl -i http://127.0.0.1:3011/`（404 を確認）
- DB 件数: `psql "$DATABASE_URL" -Atc "SELECT count(*) FROM doc; SELECT count(*) FROM chunk; SELECT count(*) FROM chunk_vec;"`
- 直近24h: `psql "$DATABASE_URL" -Atc "SELECT to_char((first_seen_at AT TIME ZONE 'Asia/Tokyo')::timestamp,'YYYY-MM-DD HH24:00'),count(*) FROM doc WHERE first_seen_at> now()-interval '24 hours' GROUP BY 1 ORDER BY 1;"`

設定整合性（ガード）
- `/etc/default/mcp-news` に固定値を保持:
  - `DATABASE_URL=postgresql://newshub_app:****@127.0.0.1:5432/newshub`
  - `APP_BIND_HOST=127.0.0.1` / `APP_BIND_PORT=3011`
  - `EMBEDDING_SPACE=e5-multilingual` / `EMBED_SPACE=e5-multilingual`
- コード側ガードにより、固定値に反すると起動時に落ちる設計（MCP-First の遵守）。

既知の詰まりと対処（今回適用済み）
- PostgreSQL 認証エラー: アプリ用ユーザ作成＋`DATABASE_URL` を資格情報つきに統一。
- EMBED_SPACE 未設定: `/etc/default/mcp-news` に追加。
- ExecStart/WorkingDirectory 不整合: `mcp-news.service`/`embed.service` を実パスに合わせて統一。

推奨の次アクション
- 任意: `newsapi-tech-jp.timer` と `hn-top.timer` の有効化（ソース拡充）。
- 任意: Nginx で API のみ公開し、`/` と `/static/` を拒否（MCP-First 推奨運用）。
- 任意: 定常監視に `journalctl -u *.service -f` とヘルスチェックを組み込み。

付記
- 詳細ログは `docs/log.md` を参照。
- 本レポートは secrets を含まない形で記載しています（DB パスワードはマスク）。

