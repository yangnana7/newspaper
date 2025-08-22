# 検証レポート（Ubuntu サーバー側）

本レポートは `ubuntu_work.md` の手順に沿って実施した結果を記録します。固定条件: DB=newshub、127.0.0.1:3011、vector(768)、cosine、UTC/JST。

## 1. 環境情報
- OS: (例) Ubuntu 24.04 LTS
- Python: (例) 3.11.x
- PostgreSQL: (例) 16 + pgvector/pg_trgm
- リポジトリ commit: (hash)
- 環境変数:
  - `DATABASE_URL=`
  - `APP_BIND_HOST=127.0.0.1`
  - `APP_BIND_PORT=3011`
  - `EMBED_SPACE/EMBEDDING_SPACE=bge-m3`
  - (任意) `RANK_ALPHA/BETA/GAMMA`, `RECENCY_HALFLIFE_HOURS`, `SOURCE_TRUST_JSON`

## 2. スキーマ/インデックス適用ログ
- `psql -f db/schema_v2.sql` 実行ログ（抜粋）
- `psql -f db/indexes_core.sql` 実行ログ（抜粋）
- インデックス一覧: `SELECT indexname FROM pg_indexes WHERE tablename IN ('doc','hint','chunk_vec')` の結果

## 3. データ投入/埋め込み
- `doc/chunk/hint` 挿入件数: (数値)
- 埋め込み実行ログ: `scripts/embed_chunks.py --space bge-m3` の出力（抜粋）
- `SELECT COUNT(*) FROM chunk_vec WHERE embedding_space='bge-m3';` の結果

## 4. API 疎通（127.0.0.1:3011）
- `/api/latest?limit=5` のレスポンス例（整形JSON）
- `/api/search?q=Hello&limit=5` のレスポンス例
- `/api/search_sem?limit=3`（qなしフォールバック）のレスポンス例
- `/api/search_sem?limit=5&space=bge-m3&q=[…]` のレスポンス例

## 5. ランク融合（任意設定の確認）
- 使用した設定: `RANK_ALPHA/BETA/GAMMA`、`RECENCY_HALFLIFE_HOURS`、`SOURCE_TRUST_JSON`
- 観察: 類似度が近い記事で、半減期を短くした場合に新着が上位化するか
- 観察: `SOURCE_TRUST_JSON` による同等記事の並び順の変化

## 6. パフォーマンス・実行計画
- `EXPLAIN ANALYZE`（ILIKE＋trgm、/api/latest、/api/search_sem 先頭候補SQL）の抜粋
- 応答時間の目安（ms）: latest/search/search_sem（q無し・q有り）

## 7. 既知の注意点/課題
- モデルDLやネットワーク制約
- ベクトルが未作成時の空配列挙動（q指定時）
- 近似HNSWの構築時間・メモリ

## 8. 結論
- 目的の機能が動作しているか（Yes/No）
- 主要エンドポイント疎通（latest/search/search_sem）
- 追加改善案

