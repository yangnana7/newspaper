# 再開用マニュアル（次回着手のための手引き）

本書は、今日の作業から中断→再開する際の最短ルートです。

## 0. 前提
- Ubuntu 22.04/24.04 LTS
- PostgreSQL 16（`pgvector` 拡張必須、PGroonga は任意）
- Python 3.11+
- リポジトリ: `/opt/mcp-news`（例）

## 1. 取得・配置
```bash
# 例: /opt へ配置
sudo mkdir -p /opt/mcp-news && sudo chown "$USER" /opt/mcp-news
cd /opt/mcp-news
# 既にクローン済みなら `git pull`
```

## 2. 依存セットアップ
```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib python3-venv python3-pip curl ca-certificates
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 3. DB 準備
```bash
# DB 作成・拡張・スキーマ適用（初回のみ）
./scripts/setup_db.sh
# もしくは手動:
# sudo -u postgres psql -c "CREATE DATABASE newshub;"
# sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS vector;"
# psql postgresql://localhost/newshub -f db/schema_v2.sql
```

## 4. 設定ファイル
```bash
cp -n config/feeds.sample.json config/feeds.json
# 必要に応じてRSSを追加
```

## 5. 単発実行（動作確認）
```bash
export DATABASE_URL=postgresql://localhost/newshub
source .venv/bin/activate
# RSS 取り込み
python scripts/ingest_rss.py --feeds config/feeds.json
# NewsAPI（要: NEWSAPI_KEY）
export NEWSAPI_KEY=xxxx
python scripts/ingest_newsapi.py --mode top --country jp --category technology --page-size 50 --pages 1
# HN
python scripts/ingest_hn.py --kind topstories --limit 50
# 埋め込み
export EMBEDDING_MODEL=intfloat/multilingual-e5-base
python scripts/embed_chunks.py --space bge-m3
# 検索（MCP）
python -m mcp_news.server  # stdio 起動
```

## 6. 定期実行（systemd）
```bash
# 環境ファイル（NEWSAPI_KEY 等）
sudo cp deploy/mcp-news.env.sample /etc/default/mcp-news
sudoedit /etc/default/mcp-news

# ingest/embed/MCP
sudo cp deploy/ingest.service /etc/systemd/system/ingest.service
sudo cp deploy/ingest.timer   /etc/systemd/system/ingest.timer
sudo cp deploy/embed.service  /etc/systemd/system/embed.service
sudo cp deploy/embed.timer    /etc/systemd/system/embed.timer
sudo cp deploy/mcp-news.service /etc/systemd/system/mcp-news.service

# NewsAPI/HN サンプル
sudo cp deploy/newsapi-tech-jp.service /etc/systemd/system/newsapi-tech-jp.service
sudo cp deploy/newsapi-tech-jp.timer   /etc/systemd/system/newsapi-tech-jp.timer
sudo cp deploy/hn-top.service          /etc/systemd/system/hn-top.service
sudo cp deploy/hn-top.timer            /etc/systemd/system/hn-top.timer

# 実パスへ置換
sudo sed -i 's#%h/mcp-news#/opt/mcp-news#g' /etc/systemd/system/*.service
sudo sed -i 's#%h/mcp-news/.venv#/opt/mcp-news/.venv#g' /etc/systemd/system/*.service

# 有効化
sudo systemctl daemon-reload
sudo systemctl enable --now ingest.timer embed.timer newsapi-tech-jp.timer hn-top.timer mcp-news.service

# ログ
journalctl -u ingest.service -n 100 --no-pager
journalctl -u embed.service -n 100 --no-pager
journalctl -u newsapi-tech-jp.service -n 100 --no-pager
journalctl -u hn-top.service -n 100 --no-pager
journalctl -u mcp-news.service -n 100 --no-pager
```

## 7. トラブルシュート
- psycopg 接続拒否: `sudo systemctl status postgresql`, 接続URI/DNS/権限を確認。
- `ERROR: could not open extension control file "vector"`: pgvector パッケージ導入と `CREATE EXTENSION vector;` 実行を確認。
- モデル取得失敗: プロキシ/ネットワーク制限を確認。オフラインの場合は事前にモデルを配布し `HF_HOME` を設定。
- NewsAPI 429: レート制限。`--sleep` を増やす、ページ数を減らす、時間帯を分散。

## 8. 次回タスクの推奨順
1) HNSW インデックス作成：`chunk_vec` に space 別で作成。
2) `semantic_search` のランク融合パラメータ化（recency/source_weight）。
3) Prometheus エクスポート（取り込み/埋め込み件数）。
4) 近重複（MinHash/SimHash）、Entity Linking（Wikidata QID）、Event 抽出（SRL/OIE）。
5) 多言語評価セット作成と `recall@10`/`nDCG@10` 計測のループ運用。

## 9. 参照
- `README_UBUNTU.md`: 詳細セットアップ/評価/セキュリティ
- `db/schema_v2.sql`: スキーマ定義
- `scripts/*`: 取り込み/埋め込み/評価スタブ
- `deploy/*`: systemd 雛形

以上。次回は 8. の順に着手するのが効率的です。

