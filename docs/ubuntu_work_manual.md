# Ubuntu側 AIエージェント向け 確認手順指示書（0823対応）

本書は、0823 指示の実装（多言語埋め込み・ランク融合・自動蓄積・MCP/HTTP共通化）をUbuntu環境で検証・記録するための具体手順です。結果は `docs/verification_report_0823.md` に転記してください。

**固定条件**
- DB: `newshub`
- バインド: `127.0.0.1:3011`（外部公開時はNginx終端。アプリはローカル待受）
- ベクトル/距離: `vector(768)`、cosine `<=>`
- 既定埋め込み空間: `e5-multilingual`

---

## 0. 事前準備（1回のみ）
- 依存導入: `sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib postgresql-16-pgvector jq`
- 仮想環境: `python3 -m venv /opt/newspaper/.venv && source /opt/newspaper/.venv/bin/activate && pip install -U pip && pip install -r requirements.txt`
- リポPATH: `export PYTHONPATH=.`

---

## 1. 環境ファイルの配置
- サンプル: `deploy/mcp-news.env.sample`
- 設置例: `sudo cp deploy/mcp-news.env.sample /etc/newshub.env && sudo chmod 600 /etc/newshub.env`
- 必須変数（例）:
  - `DATABASE_URL=postgresql://127.0.0.1:5432/newshub`
  - `ENABLE_SERVER_EMBEDDING=1`
  - `EMBEDDING_MODEL=intfloat/multilingual-e5-base`
  - `EMBED_SPACE=e5-multilingual`（互換: `EMBEDDING_SPACE=e5-multilingual`）
  - `RANK_ALPHA=0.7 RANK_BETA=0.2 RANK_GAMMA=0.1`
  - `RECENCY_HALFLIFE_HOURS=24`
  - `SOURCE_TRUST_DEFAULT=1.0`
  - `SOURCE_TRUST_JSON={}`
  - （任意）`USER_AGENT` `WORKDIR` `VENV` `FEEDS_FILE`

確認: `sudo sh -c 'set -a; . /etc/newshub.env; set +a; env | egrep "DATABASE_URL|EMBED|RANK_|RECENCY|SOURCE_TRUST"'`

---

## 2. DBとスキーマ/インデックス
- 拡張/DB:
  ```bash
  sudo -u postgres psql <<'SQL'
  CREATE DATABASE newshub;
  \c newshub
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
  SQL
  ```
- 適用:
  ```bash
  psql "$DATABASE_URL" -f db/schema_v2.sql
  psql "$DATABASE_URL" -f db/indexes_core.sql
  ```
- 確認:
  ```bash
  psql "$DATABASE_URL" -c "SELECT to_regclass('doc'), to_regclass('chunk'), to_regclass('chunk_vec');"
  psql "$DATABASE_URL" -c "SELECT indexname FROM pg_indexes WHERE tablename IN ('doc','hint','chunk_vec') ORDER BY 1;"
  ```
- レポート: 上記コマンド出力を `docs/verification_report_0823.md` へ貼付

---

## 3. データ投入と埋め込み
- サンプル投入（1件）: ubuntu_work_0823.md の「2. 最小データ投入」を実施
- 埋め込み（推奨）:
  ```bash
  source /opt/newspaper/.venv/bin/activate
  python scripts/embed_chunks.py --space e5-multilingual --batch 64 --normalize
  psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM chunk_vec WHERE embedding_space='e5-multilingual';"
  ```
- レポート: 件数・ログを貼付

---

## 4. HTTP アプリ起動と疎通
- 起動: `mkdir -p web/static && uvicorn web.app:app --host 127.0.0.1 --port 3011`
- 疎通（例）:
  ```bash
  curl -s "http://127.0.0.1:3011/api/latest?limit=5" | jq .
  curl -s "http://127.0.0.1:3011/api/search?q=Hello&limit=5&offset=0" | jq .
  curl -s "http://127.0.0.1:3011/api/search_sem?limit=3" | jq .
  ```
- レポート: レスポンスJSONを貼付

---

## 5. MCPサーバ（stdio）と順序一致確認
- 環境読込: `export $(grep -v '^#' /etc/newshub.env | xargs -d '\n')`
- 起動（手動）: `python -m mcp_news.server`（別端末/ターミナル想定）
  - 直接対話が難しい場合は関数呼出で確認:
  ```bash
  python - <<'PY'
  import os
  os.environ.setdefault('DATABASE_URL', os.getenv('DATABASE_URL','postgresql://localhost/newshub'))
  from mcp_news import server
  res = server.semantic_search('最新のAIニュース', top_k=5)
  for r in res:
      print(r.get('doc_id'), r.get('title'))
  PY
  ```
- 一致確認（Webとの順序）:
  ```bash
  VEC=$(python - <<'PY'
  import json; from sentence_transformers import SentenceTransformer
  m=SentenceTransformer('intfloat/multilingual-e5-base')
  print(json.dumps(m.encode(['最新のAIニュース'], normalize_embeddings=True)[0].tolist()))
  PY
  )
  curl -s --get --data-urlencode "q=$VEC" "http://127.0.0.1:3011/api/search_sem?limit=5&space=${EMBED_SPACE:-e5-multilingual}" | jq '.[].doc_id'
  ```
- レポート: MCP出力のdoc_id列とWeb出力のdoc_id列を併記し、同順かを所感で記述

---

## 6. ランク融合（A/B/Cケース）
- 既定 / 新着重視（`RECENCY_HALFLIFE_HOURS=1`）/ 信頼度（`SOURCE_TRUST_JSON='{"test://local":1.2}'`）を切替
- 各ケースで `/api/search_sem?limit=5&q=...` のJSONを貼付
- 変化したdoc_idと理由（新着・信頼度）を一言で記述

---

## 7. systemd タイマー（任意）
- サービス/タイマー配置:
  ```bash
  sudo cp deploy/newshub-ingest@.service /etc/systemd/system/
  sudo cp deploy/newshub-ingest@.timer   /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now newshub-ingest@$(whoami).timer
  ```
- 確認: `systemctl status newshub-ingest@$(whoami).service` / `journalctl -u newshub-ingest@$(whoami).service -n 50 --no-pager`
- レポート: 最新ログの抜粋を貼付

---

## 8. 提出
- すべてのログ・JSON・所感を `docs/verification_report_0823.md` に転記
- Pass/Fail と改善提案を最後に明記

