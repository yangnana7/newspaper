# MCPニュース集約サーバー: Ubuntu 初期実装ガイド（v2準拠）

このフォルダーには、Ubuntu サーバーにひとまず実装できる最小構成のスクリプト・スキーマ・MCPサーバー骨組みを含みます。可視化・多言語翻訳は後段（UI層）想定で、本体は AI 向けのデータ層に集中します。

## 1. 前提
- OS: Ubuntu 22.04/24.04 LTS
- DB: PostgreSQL 16（`pgvector` 必須、`PGroonga` は任意）
- ランタイム: Python 3.11+

## 2. インストール（初期セットアップ）

1) OSパッケージ

```bash
sudo apt update
sudo apt install -y curl ca-certificates git python3-venv python3-pip postgresql postgresql-contrib
```

2) pgvector / PGroonga について
- pgvector は拡張を有効化（パッケージはディストリ由来 or PGDG）。
- PGroonga は日本語検索強化用の任意拡張（必要時のみ）。

参考:
- pgvector: https://github.com/pgvector/pgvector 
- PGroonga: https://pgroonga.github.io/ 

（環境に応じて `postgresql-XX-pgvector`/`postgresql-XX-pgroonga` の apt パッケージを導入してください。導入後、DB内で `CREATE EXTENSION` を実行します）

## 3. Python 依存

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> `sentence-transformers` はモデル初回取得時に時間がかかります。サーバー側でのみ必要です。

## 4. データベース準備

```bash
# DBと拡張
sudo -u postgres psql -c "CREATE DATABASE newshub;"
sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS vector;"   # pgvector
# 任意: 日本語検索強化
# sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS pgroonga;"

# スキーマ適用（v2）
psql "postgresql://localhost/newshub" -f db/schema_v2.sql
```

接続文字列は `DATABASE_URL` 環境変数を使用します（例: `export DATABASE_URL=postgresql://localhost/newshub`）。

## 5. フィード設定

`config/feeds.sample.json` を参考に `config/feeds.json` を作成してください。

## 6. 取り込み（RSS/Atom 最小）

```bash
export DATABASE_URL=postgresql://localhost/newshub
source .venv/bin/activate
python scripts/ingest_rss.py --feeds config/feeds.json --source RSS --genre_hint medtop:04000000
```

- URL正規化、UTC変換、原文タイトル保存。
- 1記事1チャンクの最小実装（要約 or 概要があれば使用）。

## 7. ベクトル埋め込み作成

```bash
# 例: 多言語E5を使用
export EMBEDDING_MODEL=intfloat/multilingual-e5-base
python scripts/embed_chunks.py --space bge-m3  # 任意のラベル名（例）
```

- 未ベクトル化の `chunk` を対象に `chunk_vec` を作成。
- `--space` は `embedding_space` 列の識別子です（モデル名に合わせてください）。

## 8. MCP サーバー（骨組み）

```bash
# 環境
export DATABASE_URL=postgresql://localhost/newshub
export ENABLE_SERVER_EMBEDDING=1
export EMBEDDING_MODEL=intfloat/multilingual-e5-base

# 起動（stdioトランスポート）
python -m mcp_news.server
```

提供ツール（最小）:
- `semantic_search(q, top_k, since)` … ベクトル検索（なければ新着順フォールバック）
- `entity_search(ext_ids, top_k)` … mention 経由（空なら空配）
- `event_timeline(filter, top_k)` … event 経由（空なら空配）
- `doc_head(doc_id)` … タイトル等のヘッダ取得

## 9. systemd（任意）
`deploy/ingest.service` / `deploy/ingest.timer` / `deploy/mcp-news.service` を参考に配置して有効化してください。

---

注意:
- 本実装は「AIが自分で引ける」データ層に特化（v2）。翻訳・可視化は UI 層で行ってください。
- 公式API/TOS順守・レート制御・ログ・監視は運用ポリシーに従って適宜拡張してください。

## 10. pgvector／PGroonga 詳細インストール（Ubuntu）

- 目的: PostgreSQL 16 上で `vector` 拡張（必須）と `pgroonga`（任意）を有効化。

手順例（PostgreSQL Global Development Group リポジトリを利用）:

```bash
# 1) PGDG リポジトリ追加（Ubuntu 22.04/24.04）
sudo apt update && sudo apt install -y curl ca-certificates lsb-release gnupg
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/pgdg.gpg
echo "deb [arch=amd64,arm64 signed-by=/etc/apt/trusted.gpg.d/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list
sudo apt update

# 2) PostgreSQL 16 + pgvector
sudo apt install -y postgresql-16 postgresql-client-16 postgresql-16-pgvector

# 3) PGroonga（任意；PGDG用パッケージ）
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:groonga/ppa
sudo apt update
sudo apt install -y -V postgresql-16-pgdg-pgroonga

# 4) DB作成と拡張有効化
sudo -u postgres psql -c "CREATE DATABASE newshub;"
sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS vector;"
# 任意: 日本語検索強化
# sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS pgroonga;"
```

注:
- 既にUbuntu標準のPostgreSQLを使う場合は、`postgresql-16-pgvector`/`postgresql-16-pgroonga` のパッケージ名になることがあります。
- 実行環境に応じてパッケージ名が異なる場合は各公式ドキュメントを参照してください。

## 11. systemd 配置と起動手順（詳細）

前提: リポジトリを `/opt/mcp-news` に配置し、仮想環境は `/opt/mcp-news/.venv`。

```bash
# 1) 単位ファイルの配置
sudo cp deploy/ingest.service /etc/systemd/system/ingest.service
sudo cp deploy/ingest.timer   /etc/systemd/system/ingest.timer
sudo cp deploy/mcp-news.service /etc/systemd/system/mcp-news.service

# 2) WorkingDirectory と ExecStart を修正
sudo sed -i 's#%h/mcp-news#/opt/mcp-news#g' /etc/systemd/system/ingest.service /etc/systemd/system/mcp-news.service
sudo sed -i 's#%h/mcp-news/.venv#/opt/mcp-news/.venv#g' /etc/systemd/system/ingest.service /etc/systemd/system/mcp-news.service

# 3) 反映と自動起動
sudo systemctl daemon-reload
sudo systemctl enable --now ingest.timer
sudo systemctl enable --now mcp-news.service

# 動作確認
systemctl status ingest.timer
journalctl -u ingest.service -n 100 --no-pager
journalctl -u mcp-news.service -n 100 --no-pager
```

埋め込み生成を定期実行したい場合は `deploy/embed.service` / `deploy/embed.timer`（後述）も同様に配置・有効化してください。

## 11.1 NewsAPI/HN タイマー（サンプル）

環境ファイル:

```bash
sudo cp deploy/mcp-news.env.sample /etc/default/mcp-news
sudoedit /etc/default/mcp-news  # NEWSAPI_KEY を設定
```

NewsAPI（technology/jp 30分毎）:

```bash
sudo cp deploy/newsapi-tech-jp.service /etc/systemd/system/newsapi-tech-jp.service
sudo cp deploy/newsapi-tech-jp.timer   /etc/systemd/system/newsapi-tech-jp.timer
sudo sed -i 's#%h/mcp-news#/opt/mcp-news#g' /etc/systemd/system/newsapi-tech-jp.service
sudo sed -i 's#%h/mcp-news/.venv#/opt/mcp-news/.venv#g' /etc/systemd/system/newsapi-tech-jp.service
sudo systemctl daemon-reload
sudo systemctl enable --now newsapi-tech-jp.timer
```

Hacker News（topstories 15分毎）:

```bash
sudo cp deploy/hn-top.service /etc/systemd/system/hn-top.service
sudo cp deploy/hn-top.timer   /etc/systemd/system/hn-top.timer
sudo sed -i 's#%h/mcp-news#/opt/mcp-news#g' /etc/systemd/system/hn-top.service
sudo sed -i 's#%h/mcp-news/.venv#/opt/mcp-news/.venv#g' /etc/systemd/system/hn-top.service
sudo systemctl daemon-reload
sudo systemctl enable --now hn-top.timer
```

複数カテゴリ/国を回したい場合は `deploy/newsapi-tech-jp.*` を複製し、`--country/--category` を変更してください。

## 12. 評価とKPI（最小）

- 目的: ベクトル検索の実効性と取り込み健全性を継続監視。

KPI例:
- **ingest_items_total**: 取り込み件数（日次/累積）
- **vec_build_latency**: 埋め込み生成レイテンシ
- **recall@k / nDCG@k**: 多言語クエリセットでの検索品質
- **duplicates_rate**: 近重複率（将来のMinHash/SimHash導入後）

SQL例（サマリ）: `scripts/eval_metrics.sql` 参照。

簡易評価セットの雛形と recall@k 計測のstubは `scripts/eval_recall_stub.py` にあります。

## 13. 拡張ジョブ設計（サマリ）

- **ingest**: RSS/NewsAPI/HN 取り込み（現行: RSSのみ）
- **embed**: `chunk` → `chunk_vec`（多言語モデル；space別）
- **entity-link**: Wikidata/GeoNames等のIDへリンク（未実装）
- **event-extract**: S-P-O抽出→イベント化（未実装）

systemd雛形（埋め込み）:

```bash
sudo cp deploy/embed.service /etc/systemd/system/embed.service
sudo cp deploy/embed.timer   /etc/systemd/system/embed.timer
sudo sed -i 's#%h/mcp-news#/opt/mcp-news#g' /etc/systemd/system/embed.service
sudo sed -i 's#%h/mcp-news/.venv#/opt/mcp-news/.venv#g' /etc/systemd/system/embed.service
sudo systemctl daemon-reload && sudo systemctl enable --now embed.timer
```

ログ/監視:
- `journalctl -u *` で直近の実行状況を確認
- Prometheus導入時は取り込み件数やレイテンシをエクスポート（将来実装）

## 14. セキュリティ／コンプライアンス

- 公式API/TOS厳守、`robots.txt`尊重、論理削除/Retention設定
- APIキーや接続情報は `Environment=`/環境変数で注入（ハードコード禁止）
- 個人情報/著作権配慮：全文保存の最小化、要約+メタ中心

## 15. 次にやるべきこと（提案）

短期（今週）:
- NewsAPI/HackerNews コネクタ追加（APIキー設定化、レート制御）
- HNSWインデックス作成（`chunk_vec` に対し space別に）
- `semantic_search` のランク融合（recency/source_weight）をクエリパラメータ化
- 最小の Prometheus エクスポーター追加（取り込み件数/埋め込み件数）

中期（来月）:
- MinHash/SimHash による近重複クラスタリング導入
- Entity Linking パイプライン実装（Wikidata QID）→ `entity_search` 充実
- Event 抽出（SRL/OIE）→ `event_timeline` 充実
- 評価セット作成（多言語100クエリ）と CI での recall@10 / nDCG@10 追跡

運用:
- systemd 健康監視（連続失敗時の通知）
- バックアップ/リストア手順の明文化（PostgreSQL）

## 付録: 関連ドキュメント
- 最終報告書: `docs/FINAL_REPORT.md`
- 再開用マニュアル: `docs/RESUME_MANUAL.md`
## 16. NewsAPI 取り込み

前提: `NEWSAPI_KEY` を環境変数に設定（https://newsapi.org/ のAPIキー）。

例（トップヘッドライン、カテゴリーtechnology）:

```bash
export NEWSAPI_KEY=xxxx
export DATABASE_URL=postgresql://localhost/newshub
source .venv/bin/activate
python scripts/ingest_newsapi.py --mode top --country jp --category technology --page-size 50 --pages 1 --genre-hint medtop:04000000
```

検索語での全件（publishedAt順）:

```bash
python scripts/ingest_newsapi.py --mode everything --q "semiconductor OR 半導体" --page-size 50 --pages 1
```

注意:
- レート制限に注意（無料枠は厳しめ）。`--sleep` でリクエスト間隔を調整。
- `genre_hint` は任意（IPTCコードなど）。

## 17. Hacker News 取り込み

トップストーリーを100件:

```bash
export DATABASE_URL=postgresql://localhost/newshub
source .venv/bin/activate
python scripts/ingest_hn.py --kind topstories --limit 100
```

備考:
- HNはAPIキー不要。`--kind newstories|beststories` も可。
- `text` が空の場合はタイトルをチャンク化します。
