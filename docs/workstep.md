**“一般ユーザーがブラウザで目視確認できる最小UI”** を、既存のMCP/DB資産をそのまま使って Ubuntu に載せる手順をまとめました。まずは **一覧＋簡易検索（任意）** の薄いWebを FastAPI+Uvicorn で起こし、Nginx で公開します。DB・取り込み・埋め込みの最小セットアップは本プロジェクトの再開マニュアルに沿います（後述で該当箇所を引用）。

---

# ゴール（この手順の最終到達点）

* Ubuntu サーバ上で `/` にアクセスすると **最新ニュース一覧（タイトル／時刻（JST）／ソース／ジャンルヒント）** が表示される。
* バックエンドは Postgres（`doc/hint`）を直接読む極薄API（FastAPI）。
  ※ 将来は `semantic_search`（pgvectorのcos類似 `<=>`）で検索APIも拡張可。実装注意点はDay2の指示どおり cos で統一。
* ingest/embed/MCP は既存の systemd テンプレをそのまま使用。

---

## 0) 前提：DB と取り込みの初期化（既存ドキュメントどおり）

以下は既存手順の要点です。未実施なら先に通してください。

1. **依存と仮想環境**（Python 3.11 / Postgres / pgvector）

   ```bash
   sudo apt update
   sudo apt install -y postgresql postgresql-contrib python3-venv python3-pip curl ca-certificates nginx
   # リポジトリ配置
   sudo mkdir -p /opt/mcp-news && sudo chown "$USER" /opt/mcp-news
   cd /opt/mcp-news
   # ここで git clone 済みである前提（あるいは zip 展開）
   python3 -m venv .venv && source .venv/bin/activate
   pip install -U pip && pip install -r requirements.txt
   ```

   * pgvector は DB 側で `CREATE EXTENSION vector;` が必要です。エラー時は pgvector パッケージの導入を確認（「could not open extension control file "vector"」のトラブルシュート参照）。

2. **DB 作成とスキーマ適用**

   ```bash
   ./scripts/setup_db.sh
   # もしくは:
   # sudo -u postgres psql -c "CREATE DATABASE newshub;"
   # sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS vector;"
   # psql postgresql://localhost/newshub -f db/schema_v2.sql
   ```

   （`db/schema_v2.sql` は v2 モデル：doc/chunk/chunk\_vec/hint 等を定義）

3. **取り込み → 埋め込み → MCP 起動（ローカル確認）**

   ```bash
   export DATABASE_URL=postgresql://localhost/newshub
   source .venv/bin/activate
   # RSS 取り込み
   python scripts/ingest_rss.py --feeds config/feeds.json
   # 埋め込み（必要時）
   export EMBEDDING_MODEL=intfloat/multilingual-e5-base
   python scripts/embed_chunks.py --space bge-m3
   # MCP（stdio; 確認用）
   python -m mcp_news.server
   ```

   ingest/embed/MCP の **systemd 雛形**一式は `deploy/*` にあり、`/etc/systemd/system` にコピーして `enable --now` で起動します（環境ファイル `/etc/default/mcp-news` を併用）。

> 参考：現行の検索は **cos距離に統一**（`ORDER BY v.emb <=> %s`、埋め込みは正規化）で整合済。HNSWインデックスは `vector(768)` で作成（`idx_chunk_vec_hnsw_bge_m3_cos`）。

---

## 1) Web（人間UI）を最小構築：FastAPI+Uvicorn

**目的**：Postgres の `doc` と `hint(key='genre_hint')` を読むだけの薄いAPI＋静的UI。

### 1-1. 追加インストール

```bash
cd /opt/mcp-news
source .venv/bin/activate
pip install fastapi uvicorn jinja2 python-multipart
```

### 1-2. ディレクトリとコード配置

```bash
mkdir -p web/templates web/static
```

**`web/app.py`**

```python
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os, psycopg
from datetime import timezone
import zoneinfo

JST = zoneinfo.ZoneInfo("Asia/Tokyo")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")

app = FastAPI(title="MCP News – Minimal UI")
app.mount("/static", StaticFiles(directory="web/static"), name="static")

def row_to_dict(r):
    # r: doc_id, title_raw, published_at(UTC), genre_hint, url_canon, source
    ts = r[2].astimezone(JST).isoformat(timespec="seconds")
    return {"doc_id": r[0], "title": r[1], "published_at": ts,
            "genre_hint": r[3], "url": r[4], "source": r[5]}

@app.get("/api/latest")
def api_latest(limit: int = Query(50, ge=1, le=200)):
    sql = """
      SELECT d.doc_id, d.title_raw, d.published_at,
             (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
             d.url_canon, d.source
      FROM doc d
      ORDER BY d.published_at DESC
      LIMIT %s
    """
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    return [row_to_dict(r) for r in rows]

# （任意）超簡易タイトル検索（PGroongaなしでも ILIKE で動く）
@app.get("/api/search")
def api_search(q: str, limit: int = Query(50, ge=1, le=200)):
    sql = """
      SELECT d.doc_id, d.title_raw, d.published_at,
             (SELECT val FROM hint WHERE doc_id=d.doc_id AND key='genre_hint') AS genre_hint,
             d.url_canon, d.source
      FROM doc d
      WHERE d.title_raw ILIKE %s
      ORDER BY d.published_at DESC
      LIMIT %s
    """
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, (f"%{q}%", limit)).fetchall()
    return [row_to_dict(r) for r in rows]

# ルート：静的HTML
@app.get("/", response_class=HTMLResponse)
def index():
    with open("web/templates/index.html", "r", encoding="utf-8") as f:
        return f.read()
```

**`web/templates/index.html`**（超シンプルSPA）

```html
<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MCP News – Minimal UI</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:24px}
h1{margin:0 0 12px} .toolbar{display:flex;gap:8px;margin:12px 0}
.card{border:1px solid #ddd;border-radius:10px;padding:12px;margin:8px 0}
.meta{font-size:12px;color:#555}
input,button{padding:8px;border:1px solid #ccc;border-radius:8px}
button{cursor:pointer}
</style>
<h1>MCP News – Latest</h1>
<div class="toolbar">
  <input id="q" placeholder="タイトルに含まれる語で検索（任意）">
  <button onclick="runSearch()">検索</button>
  <button onclick="loadLatest()">最新を表示</button>
</div>
<div id="list"></div>
<script>
async function render(items){
  const root=document.getElementById('list'); root.innerHTML='';
  if(!items.length){ root.innerHTML='<p>該当なし。</p>'; return; }
  for(const it of items){
    const div=document.createElement('div'); div.className='card';
    div.innerHTML = `
      <div><a href="${it.url}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a></div>
      <div class="meta">${it.published_at} ｜ ${escapeHtml(it.source || '')} ｜ ${escapeHtml(it.genre_hint || '')}</div>`;
    root.appendChild(div);
  }
}
function escapeHtml(s){return s? s.replace(/[&<>"']/g, m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;' }[m])):''}
async function loadLatest(){ const r=await fetch('/api/latest?limit=50'); render(await r.json()); }
async function runSearch(){
  const q=document.getElementById('q').value.trim();
  if(!q){ return loadLatest(); }
  const r=await fetch('/api/search?'+new URLSearchParams({q,limit:50}));
  render(await r.json());
}
loadLatest();
</script>
</html>
```

> `published_at` は DB では **UTC** 保存、UI では **JST (+09:00)** 表示にしています（プロジェクト方針どおり）。

### 1-3. ローカル起動（開発）

```bash
cd /opt/mcp-news
source .venv/bin/activate
uvicorn web.app:app --host 127.0.0.1 --port 8000 --reload
# → http://127.0.0.1:8000
```

---

## 2) systemd 常駐化（Web）

既存の ingest/embed/MCP と同じ運用流儀で Web も常駐させます。

1. **環境ファイル**（すでに `/etc/default/mcp-news` を流用推奨。`DATABASE_URL` などが入る想定）

2. **サービスユニット**

```bash
sudo tee /etc/systemd/system/newshub-web.service >/dev/null <<'UNIT'
[Unit]
Description=Newshub Web (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
User=%i
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RuntimeDirectory=mcp-news
# 取り込みと同時起動での衝突は基本なし。必要なら flock も可（ingest例に準拠）。
# ExecStartPre=/usr/bin/flock -n /run/mcp-news/web.lock -c 'true'

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now newshub-web.service
journalctl -u newshub-web.service -n 100 --no-pager
```

---

## 3) Nginx で公開（80番）

```bash
sudo tee /etc/nginx/sites-available/newshub >/dev/null <<'NG'
server {
    listen 80 default_server;
    server_name _;
    client_max_body_size 2m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    # （任意）/static をキャッシュ
    location /static/ {
        proxy_pass http://127.0.0.1:8000/static/;
        expires 1h;
        add_header Cache-Control "public";
    }
}
NG
sudo ln -sf /etc/nginx/sites-available/newshub /etc/nginx/sites-enabled/newshub
sudo nginx -t && sudo systemctl reload nginx
```

> 公開前に **取り込みが実際に走っている**（`doc` にデータがある）ことを確認すると UI が空にならず安心です。`journalctl -u ingest.service` などで直近ログを確認可能。

---

## 4) スモークテスト

```bash
# DB に何件か入っている前提
curl -s http://127.0.0.1/api/latest | jq '.[0]'
# → { "doc_id":..., "title":"...", "published_at":"2025-08-21T..+09:00", ... }
```

* 画面でタイトルのクリック → 元記事へ遷移。
* `検索` ボタンにキーワードを入れてヒットするか（暫定は ILIKE）。
  ※ 将来は **pgvector (cos)** で `/api/search` を置き換え可：cos統一は Day2 指示のとおり。

---

## 5) （任意・発展）セマンティック検索APIの実装メモ

* 既存の `chunk_vec` は **正規化埋め込み × cos 距離 `<=>`** 前提。右辺は `pgvector.psycopg.Vector` で型一致させる。
* `embedding_space='bge-m3'` を必ず WHERE で縛る。インデックスは `idx_chunk_vec_hnsw_bge_m3_cos` を使用。
* モデルは `intfloat/multilingual-e5-base` 等（既存スクリプトと合わせる）。UI 側は API にクエリ文字列を渡すだけ。

---

## 6) 運用（既存タイマーの有効化）

取り込みと埋め込み、NewsAPI/HN のサンプルタイマーは雛形が用意済み。`/opt → /etc/systemd/system` に配置・有効化・ログ確認までの流れは下記のとおりです。

```bash
# 環境ファイル
sudo cp deploy/mcp-news.env.sample /etc/default/mcp-news
sudoedit /etc/default/mcp-news   # DATABASE_URL, NEWSAPI_KEY など設定

# ユニット配置
sudo cp deploy/ingest.service /etc/systemd/system/ingest.service
sudo cp deploy/ingest.timer   /etc/systemd/system/ingest.timer
sudo cp deploy/embed.service  /etc/systemd/system/embed.service
sudo cp deploy/embed.timer    /etc/systemd/system/embed.timer
sudo cp deploy/mcp-news.service /etc/systemd/system/mcp-news.service

sudo sed -i 's#%h/mcp-news#/opt/mcp-news#g' /etc/systemd/system/*.service
sudo sed -i 's#%h/mcp-news/.venv#/opt/mcp-news/.venv#g' /etc/systemd/system/*.service

sudo systemctl daemon-reload
sudo systemctl enable --now ingest.timer embed.timer mcp-news.service
journalctl -u ingest.service -n 100 --no-pager
journalctl -u embed.service -n 100 --no-pager
journalctl -u mcp-news.service -n 100 --no-pager
```

---

## 7) よくある詰まりどころ（抜粋）

* **pgvector 拡張が見つからない** → pgvector パッケージ導入＆ `CREATE EXTENSION vector;` を実行。
* **モデル取得が遅い／失敗** → プロキシ・ネットワークを確認。必要なら事前配布して `HF_HOME` を設定。
* **UIが空** → ingest が走っていない／`config/feeds.json` が空。まず RSS 1本でも入れて取り込み。

---

## 8) セキュリティと公開の注意

* まずは **社内NW／Basic認証付き** で公開推奨（Nginx で `auth_basic`）。
* NewsAPI キー等は **/etc/default/mcp-news** に置き、リポジトリへコミットしない（既存ユニットは EnvironmentFile 前提）。

---

### 補足：なぜこの構成？

* 既存の **v2データ層（doc/chunk/vec/hint）** を変更せず、人間UIだけ薄く足す思想です。UI側は必要最小の整形（JST化・ジャンル表示）に留め、**検索ロジックはサーバ側（pgvector/cos）で正しく保つ**のが中長期に安全です。

---

ここまでで、「Ubuntuサーバー整備 → 一般ユーザーが目視できるWeb一覧」の導線は完成です。
