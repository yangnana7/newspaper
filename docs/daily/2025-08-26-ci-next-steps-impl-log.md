# 2025-08-26 作業ログ（MCPニュース／CI安定化 次ステップ実施）

実施者: Codex CLI
対象: `docs/0826# MCPニュース／CI安定化 — 次ステップ指示書 & 完了確認チェックシード.md`

## 変更サマリ
- 追加: `db/migrations/2025-08-27_mention_span_default.sql`
  - `ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);`
- 変更: `.github/workflows/ci.yml`
  - `pytest` 実行を `tee ci_fail.log` でログ保存し、失敗時に `actions/upload-artifact@v4` で `ci-fail-log` をアップロード
- 追加: `config/near_duplicate.yaml`
  - `simhash_hamming_max: 12`, `jaccard_min: 0.35`
- 変更: `search/near_duplicate.py`
  - `load_thresholds_from_yaml()` を追加（`config/near_duplicate.yaml` の読み込み＆ログ出力）
  - `cluster_by_simhash_with_config()` を追加
- 変更: `scripts/cluster_duplicates.py`
  - YAML 閾値を取り込み、SimHash/Jaccard の閾値を上書き可能化（ログ出力あり）

## テスト
実行: `APP_BIND_HOST=127.0.0.1 APP_BIND_PORT=3011 DATABASE_URL=postgresql://127.0.0.1/newshub EMBED_SPACE=e5-multilingual SKIP_DB_TESTS=1 pytest -q`

結果: `24 passed, 5 skipped`

## DoD チェック（本リポ内での確認）
- [x] CI 設定: 失敗時 Artifact アップロードの行追加（`ci-fail-log`）
- [x] マイグレーション追加: `mention.span` の DEFAULT 設定ファイルを追加
- [x] 近重複設定: 実行時に `near_duplicate.yaml` をロードしログを出す実装を追加
- [x] ドキュメント: `docs/UI_MANUAL.md` は既に curl サンプル掲載済み（/api/latest, /api/search, /api/search_sem, /api/events, /metrics）
- [ ] CI 緑化（GitHub 上）: リモートCIの実行はリポジトリ側で要確認
- [ ] DB マイグレーション適用確認: 本番/検証DBで `\\d mention` に DEFAULT 反映を確認要
- [ ] staging Ops: `linking.timer`/`events_ingest.timer` の稼働は環境で要確認

## 補足
- `near_duplicate.yaml` は未存在でも安全に既定値へフォールバックします。
- ログ: `search.near_duplicate` ロガーで `near_duplicate.yaml loaded` を `INFO` 出力します。

