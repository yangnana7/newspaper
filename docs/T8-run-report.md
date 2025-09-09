T8 実施レポート（Backup/Restore + systemd）

実施日: 
担当: 

実施内容
- 追加: `scripts/newshub-backup.sh`, `scripts/newshub-verify.sh`
- 追加: `deploy/newshub-backup.service|timer`, `deploy/newshub-verify.service|timer`
- 追加: `deploy/install-backup.sh`
- ドキュメント: `docs/T8-backup-restore.md`

セットアップ・ログ（要点）
1) インストール
```
sudo bash deploy/install-backup.sh
```
2) タイマー確認
```
systemctl list-timers --all | egrep 'newshub-(backup|verify)'
```
出力抜粋:
```
Fri 2025-09-05 03:30:00 JST 5h 18min -                                      - newshub-backup.timer           newshub-backup.service
Sun 2025-09-07 04:10:00 JST   2 days -                                      - newshub-verify.timer           newshub-verify.service
```

3) 手動バックアップ（任意）
```
sudo systemctl start newshub-backup.service
journalctl -u newshub-backup.service -n 50 --no-pager
ls -l /var/backups/newshub | tail -n 5
cd /var/backups/newshub && sha256sum -c newshub-*.sha256 | tail -n 3
```
出力抜粋:
```
... newshub-backup.service: Starting ...
[OK] backup done: /var/backups/newshub/newshub-20250904-221255.dump

drwxrws--- 2 root     postgres     4096  9月  4 22:13 app
-rw-r--r-- 1 postgres postgres 47421083  9月  4 22:13 newshub-20250904-221255.dump
-rw-r--r-- 1 postgres postgres       95  9月  4 22:13 newshub-20250904-221255.dump.sha256
newshub-20250904-221255.dump: OK
```

4) 週次検証の手動実行（受入確認）
```
sudo systemctl start newshub-verify.service
journalctl -u newshub-verify.service -n 100 --no-pager
```
出力抜粋（件数と indexdef 抜粋、末尾 `[OK] verify done`）:
```
[INFO] vector_cosine_ops indexes on chunk_vec (if any)
hnsw_chunk_vec_bgem3_cos|CREATE INDEX hnsw_chunk_vec_bgem3_cos ON public.chunk_vec USING hnsw (emb vector_cosine_ops) WHERE (embedding_space = 'bge-m3'::text)
idx_chunk_vec_hnsw_bge_m3_cos|CREATE INDEX idx_chunk_vec_hnsw_bge_m3_cos ON public.chunk_vec USING hnsw (emb vector_cosine_ops) WHERE (embedding_space = 'bge-m3'::text)
idx_chunk_vec_hnsw_e5_cos|CREATE INDEX idx_chunk_vec_hnsw_e5_cos ON public.chunk_vec USING hnsw (emb vector_cosine_ops) WHERE (embedding_space = 'e5-multilingual'::text)
ix_chunk_vec_bge_m3_hnsw|CREATE INDEX ix_chunk_vec_bge_m3_hnsw ON public.chunk_vec USING hnsw (emb vector_cosine_ops) WHERE (embedding_space = 'bge-m3'::text)
[OK] verify done for /var/backups/newshub/newshub-20250904-221255.dump
```

所見/メモ
- ENV 参照は `/etc/default/mcp-news` の `DATABASE_URL` 固定（MCP-First ルールに準拠）
- HNSW/`vector_cosine_ops` の検出を verify に同梱（残件吸収）
- さらなる強化: rclone オフサイト同期 / GPG 暗号化（任意）

補足（実装上の調整）
- バックアップ先ディレクトリの権限を `2770 root:postgres` へ調整（`postgres` が書込可＋setgidでグループ継承）。
- verify スクリプトは DB 作成/削除時に `psql -d postgres` を使用、復元時は `--dbname=newshub_verify` を指定し、アプリ用ユーザに CREATE DATABASE 権限が不要となるよう修正。
