# 最終報告書（初期実装・Day 1）

日付: 2025-08-20 (JST)
対象: MCPニュース集約サーバー（Ubuntu）
スコープ: /docs の v1→v2 方針に基づく、AIネイティブ検索用データ層の最小実装と運用雛形

## 1. 背景と要旨
- v1: RSS/NewsAPI を中心に正規化→重複排除→ジャンル付与→MCP で公開。
- v2: 人間UIを後回しにし、AIが直接引けるデータ層を最小化（Doc/Chunk/Vector + Entities/Events）。
- 本日の成果は v2 方針に準拠し、Ubuntu 上でひとまず動かせる骨組み（スキーマ・取り込み・埋め込み・MCP）を整備。

## 2. 追加・変更ファイル一覧
- ドキュメント
  - `README_UBUNTU.md`: セットアップ/運用の手順（詳細章を含む）
  - `docs/FINAL_REPORT.md`: 本書
  - `docs/RESUME_MANUAL.md`: 再開用マニュアル
- スキーマ
  - `db/schema_v2.sql`: v2 データモデル（doc/chunk/chunk_vec/entity/…）と一意制約
- 依存
  - `requirements.txt`: mcp, psycopg, pgvector, feedparser, sentence-transformers, httpx, ほか
- スクリプト
  - 取り込み: `scripts/ingest_rss.py`, `scripts/ingest_newsapi.py`, `scripts/ingest_hn.py`
  - 埋め込み: `scripts/embed_chunks.py`
  - 評価: `scripts/eval_metrics.sql`, `scripts/eval_recall_stub.py`
  - 拡張スタブ: `scripts/entity_link_stub.py`, `scripts/event_extract_stub.py`
  - DB 初期化: `scripts/setup_db.sh`
- MCP サーバー
  - `mcp_news/server.py`, `mcp_news/db.py`, `mcp_news/__init__.py`
- デプロイ雛形（systemd）
  - 定期取り込み: `deploy/ingest.service|timer`, `deploy/newsapi-tech-jp.service|timer`, `deploy/hn-top.service|timer`
  - 埋め込み: `deploy/embed.service|timer`
  - サーバー: `deploy/mcp-news.service`
  - 環境: `deploy/mcp-news.env.sample`

## 3. できること（現時点）
- RSS/NewsAPI/Hacker News から原文タイトル・概要を取得し、`doc` + 最小 `chunk` 保存。
- `chunk` から pgvector に埋め込み（多言語モデル）を保存。
- MCP サーバーで `semantic_search`（埋め込み有→ベクトル検索/無→新着順）、`doc_head` などを提供。
- systemd タイマーで ingest/embed/NewsAPI/HN を定期実行可能。

## 4. 想定する運用フロー（ダイジェスト）
1) DB と拡張（pgvector）用意 → `db/schema_v2.sql` 適用。
2) フィード設定 → `scripts/ingest_rss.py` / `scripts/ingest_newsapi.py` / `scripts/ingest_hn.py` を実行。
3) `scripts/embed_chunks.py` で未ベクトル化 `chunk` に埋め込み付与。
4) `python -m mcp_news.server` で MCP を起動（stdio）。
5) systemd で ingest/embed を定期実行。

## 5. 検証観点（最小）
- スキーマ適用: `psql -d newshub -c "\d doc"` でテーブル作成を確認。
- 取り込み: `SELECT count(*) FROM doc;` が >0。
- 埋め込み: `SELECT count(*) FROM chunk_vec;` が >0。
- 検索: MCP 経由または直接SQLで数件取得できること。
- メトリクス: `scripts/eval_metrics.sql` でサマリ確認。`scripts/eval_recall_stub.py` は評価セット準備後に使用。

## 6. リスク・留意
- NewsAPI はレート/利用規約に注意。`--sleep` で調整、APIキーは環境変数で注入。
- sentence-transformers のモデル取得は容量/時間がかかる。サーバー側の初回のみ発生。
- 日本語検索の高度化は PGroonga 併用を推奨（今回は任意）。
- 近重複・Entity/Event は枠のみ（stub）。段階的に導入。

## 7. 次にやるべきこと（優先順）
- HNSW インデックス作成（space単位）
- `semantic_search` のランク融合（recency/source_weight）をパラメータ化
- Prometheus エクスポート（取り込み/埋め込み件数）
- NewsAPI カテゴリ/国のテンプレート化（複数ジョブ展開）
- HN 再実行最適化（前回ID/時刻の保持）
- 近重複（MinHash/SimHash）→ Entity Linking（Wikidata QID）→ Event 抽出（SRL/OIE）
- 多言語評価セット作成と `recall@10`/`nDCG@10` の継続計測

以上で初日スコープは完了です。詳細手順・再開方法は `docs/RESUME_MANUAL.md` を参照ください。

---

## 付記（2025-08-21 更新）
- ベクトル検索を cos 距離に統一し、`chunk_vec.emb` を `vector(768)` に設定（HNSWの要件）。
- スキーマの補助インデックス作成順序を修正（テーブル定義後に作成）。
- CIを強化：`PYTHONPATH=.` でテスト実行、依存の `psycopg[binary] pgvector` を明示インストール。
