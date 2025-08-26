# 0826# MCPニュース／CI安定化 — DoD チェックシード（2025-08-26）

対象ドキュメント: `docs/0826# MCPニュース／CI安定化 — 次ステップ指示書 & 完了確認チェックシード.md`
実施者: Codex CLI

## チェック結果
- [ ] CI 緑化（master 最新コミットが緑）
  - 備考: GitHub Actions 上で要確認（ローカルでは未検証）。
- [x] pytest（ローカル）: `SKIP_DB_TESTS=1 pytest -q` が pass
  - 実行結果: `24 passed, 5 skipped`
  - 実行環境: `APP_BIND_HOST=127.0.0.1 APP_BIND_PORT=3011 DATABASE_URL=postgresql://127.0.0.1/newshub EMBED_SPACE=e5-multilingual`
- [ ] DB マイグレーション: `\\d mention` で `span` の DEFAULT に `int4range(0,0)`
  - 備考: マイグレーションファイルは追加済み（`db/migrations/2025-08-27_mention_span_default.sql`）。適用確認は DB 環境で要実施。
- [ ] CI artifact: わざと失敗させた際に `ci-fail-log` が Artifacts に出る
  - 備考: `.github/workflows/ci.yml` に upload 設定追加済み。リモート CI 上で要検証。
- [ ] 近重複設定: 実行時ログに `near_duplicate.yaml` のロード痕跡
  - 備考: `search/near_duplicate.py` にローダと INFO ログを実装。実運用プロセスのログで要確認。
- [ ] staging Ops: `linking.timer`/`events_ingest.timer` が active、メトリクス増分
  - 備考: systemd が稼働する staging 環境で要確認。
- [x] ドキュメント: `docs/UI_MANUAL.md` に curl サンプルが記載
  - 備考: 既に `/api/latest`, `/api/search`, `/api/search_sem`, `/api/events`, `/metrics` の curl が記載済み。

## 実装差分（抜粋）
- 追加: `db/migrations/2025-08-27_mention_span_default.sql`
- 変更: `.github/workflows/ci.yml`（pytest ログ保存＋失敗時 artifact）
- 追加: `config/near_duplicate.yaml`
- 変更: `search/near_duplicate.py`（YAML ロード＋ログ、ヘルパー追加）
- 変更: `scripts/cluster_duplicates.py`（YAML 閾値の適用とログ）

## 次アクション（担当者向け）
- GitHub Actions の実行結果で `ci-fail-log` アーティファクトの挙動を確認
- 検証/本番 DB でマイグレーション適用後、`\\d mention` で DEFAULT を確認
- staging で `linking.timer` / `events_ingest.timer` の稼働とメトリクス増分を確認
