T8: Backup/Restore + systemd（運用手順）

概要
- 対象: PostgreSQL `newshub`
- 方式: `pg_dump` custom `.dump` + SHA256
- 保存先: `/var/backups/newshub`（`root:postgres`, `0750`）
- 世代保持: 21日
- 週次検証: `newshub_verify` に `pg_restore` → 件数・index確認後に破棄
- スケジュール: 日次 03:30（backup）、週次 日曜 04:10（verify）

インストール
- 必要条件: `psql`, `pg_dump`, `pg_restore` が利用可能、`/etc/default/mcp-news` に `DATABASE_URL=postgresql://127.0.0.1:5432/newshub`
- 実行:
  - `sudo bash deploy/install-backup.sh`

構成概要
- スクリプト: `scripts/newshub-backup.sh`, `scripts/newshub-verify.sh` → `/usr/local/bin/` に配置
- ユニット/タイマー: `deploy/newshub-*.service|timer` → `/etc/systemd/system/`

受入基準（Done）
- `systemctl list-timers` に `newshub-backup.timer` と `newshub-verify.timer` が active
- `/var/backups/newshub/` に `newshub-YYYYMMDD-HHMMSS.dump` と `...sha256`
  - `cd /var/backups/newshub && sha256sum -c newshub-*.sha256` が OK
- `sudo systemctl start newshub-verify.service` が成功し、ログ末尾が `[OK] verify done`
- 任意: `app/app-YYYYMMDD.tgz` に `/etc/default/mcp-news` と `mcp-news.service` を含む

障害時のフルリストア（手動）
1) 最新ダンプ特定: `latest=$(ls -1t /var/backups/newshub/newshub-*.dump | head -n1)`
2) 停止: `sudo systemctl stop mcp-news.service ingest.timer embed.timer || true`
3) DB初期化+復元:
   - `eval "$(grep -E '^DATABASE_URL=' /etc/default/mcp-news)"`
   - `sudo -u postgres psql -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS newshub;"`
   - `sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE newshub;"`
   - `pg_restore --clean --if-exists --no-owner --no-privileges --dbname="$DATABASE_URL" "$latest"`
4) 起動: `sudo systemctl start mcp-news.service ingest.timer embed.timer`
5) スモーク: `/search` が 200/204、`/` が 404

メモ
- Verify は vector_cosine_ops の index がある場合に検出（HNSWの再確認サブタスク対応）。
- UI は MCP-First により既定無効（T7 の方針を踏襲）。

