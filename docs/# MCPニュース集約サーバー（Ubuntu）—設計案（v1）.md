# MCPニュース集約サーバー（Ubuntu）—設計案（v1）

## 0. ゴールと必須要件

* **対象**：あらゆるジャンルのニュース／ネット最新情報（一般ニュース、テック、金融、ゲーム/アニメ、スポーツ、科学、地域…）
* **出力必須**：`title`（タイトル）、`published_at`（時間・タイムゾーン付き）、`genre`（推定ジャンル名）
* **形態**：**MCPサーバー**として提供（LLMクライアントから「ツール」「リソース」で呼べる）。MCPはLLM⇄外部データ連携のオープン標準。Python SDKあり。 ([Model Context Protocol][1], [Anthropic][2], [GitHub][3])

---

## 1. 全体アーキテクチャ（モジュール分割）

```
[Connectors]  RSS/Atom, NewsAPI, GDELT, HN/Reddit/YouTube(任意)
      │
      ▼
[Normalizer]  共通スキーマ化（title/url/source/published_at/author/lang）
      │
      ├─[Deduplicator]  URL正規化＋MinHash/SimHash
      │
      ├─[Classifier]   ジャンル推定（規則＋ゼロショット）
      │
      ▼
[Store]  PostgreSQL(+PGroonga) / Meilisearch(任意) / オブジェクトストレージ
      │
      ▼
[MCP Server]  tools/resources: latest_news, search_news, summarize, feeds.list など
      │
      ▼
[Clients]  Claude/ChatGPT等のMCP対応クライアント、CLI, APIゲートウェイ
```

* **MCP**：Tools（実行系）とResources（参照系）で公開。Streamable HTTP or stdio transport。 ([Model Context Protocol][4], [GitHub][5])
* **Ingestion**：まずRSS/Atom＋公式API中心（TOS準拠・安定・軽量）。 ([RSSアドバイザリーボード][6], [IETF Datatracker][7])

---

## 2. コネクタ設計（一次情報優先）

### 必須（MVPで導入）

* **RSS/Atom**：ほぼ全サイト対応。失敗時も劣化に強い。 ([RSSアドバイザリーボード][6], [IETF Datatracker][7])
* **NewsAPI**（商用API／無償枠有）：国別・カテゴリ・キーワードで網羅。ジャンル付与の素地に使える。 ([ニュースAPI][8])
* **Hacker News API**（テック系の“ネット最新”）：軽量JSON。必要ならAlgolia検索APIも併用。 ([GitHub][9], [HN Search][10])

### 拡張（必要に応じて）

* **GDELT**：グローバルな出来事メタデータ（GKG/Events）。地政・国際ニュース補完。 ([GDELT Project][11], [data.gdeltproject.org][12], [geomesa.org][13])
* **Reddit/YouTube/各SNS**：**必ず公式API/TOS遵守**で。レート制限と認可の実装前提（ここではMVP範囲外として後日モジュール化）。
  （例：YouTube Data API v3／Reddit API）

---

## 3. データ正規化スキーマ（PostgreSQL）

```sql
CREATE TABLE items (
  id BIGSERIAL PRIMARY KEY,
  source      TEXT NOT NULL,             -- feed名 or API名
  source_uid  TEXT,                      -- API固有ID（HN item_id等）
  url         TEXT UNIQUE,               -- 正規化後URL（canonical）
  title       TEXT NOT NULL,
  summary     TEXT,
  author      TEXT,
  lang        TEXT,                      -- 'ja','en',...
  published_at TIMESTAMPTZ NOT NULL,     -- 供給元時刻→UTC→保存
  first_seen_at TIMESTAMPTZ NOT NULL,    -- 取得時刻
  genre       TEXT,                      -- 推定ジャンル（第一層）
  genre_conf  REAL,                      -- 確信度 0..1
  topics      TEXT[],                    -- サブトピック/タグ
  raw         JSONB                      -- 生ペイロード
);
CREATE INDEX idx_items_published ON items (published_at DESC);
CREATE INDEX idx_items_genre ON items (genre);
```

* 日本語検索の実用性確保に**PGroonga**を推奨（PostgreSQLネイティブ全文検索は日本語が弱い）。 ([pgroonga.github.io][14], [PostgreSQL][15], [Supabase][16])
* 代替に **Meilisearch** を併用しても良い（高速ファセット＋日本語プラグイン）。

**時間**：保存はUTC、レスポンスで `Asia/Tokyo` へ変換（ISO 8601 `+09:00` を明示）。

---

## 4. 重複排除（ニュース特有の“同一事件多面記事”対策）

1. **URL正規化**（UTM除去・スラッグ標準化）
2. **本文要約／タイトルの** n-gram → **MinHash+LSH** で近傍検出
3. 類似度しきい値を超えたものを**代表1件に集約**（クラスターID付与）

参考：ニュース近重複の研究・実装（MinHash/SimHash・オンライン検出）。 ([Google Research][17], [ACLア Anthology][18], [distilabel.argilla.io][19], [ACM Digital Library][20])

---

## 5. ジャンル推定（`genre` の決定）

**戦略：規則ベース × ゼロショットのハイブリッド**

* **第1段（高速規則）**

  * 供給元カテゴリ（NewsAPIのカテゴリ等）→内部ジャンルにマップ
  * 主要キーワード辞書（例：決算/金利→“金融・マーケット”）
  * 地域ドメイン/セクション（sports/techなど）
* **第2段（ゼロショット）**

  * ラベル集合：**IPTC Media Topics** 第1層17ジャンルを採用（日本語ラベルもあり）。スコア上位を採用・閾下は“general”。 ([IPTC][21], [show.newscodes.org][22])
  * 実装は軽量埋め込み＋最近傍、または日本語NLI系でのゼロショット（例：bert-base-japanese-jsnli）。 ([Hugging Face][23])

> IPTCはメディア向けの標準分類で運用実績・多言語対応あり。将来の細分化（tier 2/3）も容易。 ([IPTC][24], [geneea.com][25])

**出力例（最低限）：**

```json
{
  "title": "米CPIが市場予想を下回る",
  "published_at": "2025-08-19T12:34:00+09:00",
  "genre": "economy, business and finance"
}
```

---

## 6. MCPサーバー設計（公開インターフェース）

**Tools（実行）**

* `latest_news(limit:int=50, genres:list[str]|None, since_iso:str|None) -> [Item]`
* `search_news(q:str, genres:list[str]|None, since_iso:str|None) -> [Item]`
* `summarize(url_or_id:str, max_chars:int=500) -> {summary, topics[]}`
* `feeds.list() -> [ {source, kind, rate_limit} ]`

**Resources（参照）**

* `news://latest?genre=tech&limit=50`
* `news://item/{id}`

Python公式SDK（FastMCP）で**型付きの構造化出力**を返す。HTTP/stdioいずれも可。 ([GitHub][5])

---

## 7. Ubuntuデプロイ／運用

### 推奨スタック

* **OS**：Ubuntu 22.04/24.04 LTS
* **ランタイム**：Python 3.11+（`uv`/`poetry`管理）、Node不要
* **DB**：PostgreSQL 16 + **PGroonga**（日本語検索強化） ([pgroonga.github.io][14])
* **ジョブ**：`systemd` timer（5〜10分間隔ポーリング）
* **監視**：Prometheus + Grafana、構成は後述。

### ひな形コマンド

```bash
# ベース
sudo apt update && sudo apt install -y postgresql postgresql-contrib nginx
# PGroonga (公式手順に従う)
# Python
curl -LsSf https://astral.sh/uv/install.sh | sh
uv init mcp-news && cd mcp-news
uv add "mcp[cli]" psycopg[binary] feedparser httpx pydantic simhash datasketch pytz
# （必要に応じて）MeCab/SudachiPy系、日本語NLP
```

SudachiPyは現行ドキュメントに沿って`from sudachipy import Tokenizer`等で利用（古いimportは非推奨）。 ([worksapplications.github.io][26])

### systemd（例：ingest.timer）

* `ingest.service`：コネクタ実行→正規化→DB投入→MCPへ更新通知
* `ingest.timer`：`OnCalendar=*:0/10`（10分毎）

---

## 8. コネクタ実装ポリシー

* **RSS/Atom**：`feedparser`で`title/link/summary/published`抽出。RSS/Atom仕様準拠で堅牢。 ([RSSアドバイザリーボード][6], [IETF Datatracker][7])
* **NewsAPI**：国/カテゴリ/キーワードをクエリ。メタの`source`や`category`を**規則ベース分類の第一材料**に。 ([ニュースAPI][27])
* **HN**：`/v0/topstories`→個別`/item/{id}`の逐次取得。検索はAlgolia APIで高速化可能。 ([GitHub][9], [HN Search][10])
* **GDELT**：重大イベントの補完用（解析/指標）。 ([GDELT Project][11], [data.gdeltproject.org][12])
* **法令/TOS順守**：クロールはrobots.txtとサイト規約を厳守。APIキー・レートリミットを設定化。

---

## 9. 品質担保

* **重複指標**：Jaccard（MinHash）とSimHashの二段判定。ニュース特有の「同テーマ・別記事」をクラスタ化。 ([Google Research][17], [ACLア Anthology][18])
* **分類精度**：IPTC第1層のF1を週次計測（ラベル付き評価セットを少量作成）。
* **回帰**：主要フィードのSLA監視（連続失敗/0件検出をAlert）。

---

## 10. セキュリティ／運用

* **認証**：MCPサーバー側にOAuthトークン検証（SDKがサポート）。社内公開やAPIゲートの前段に。 ([GitHub][5])
* **レート制御**：各コネクタごとにトークンバケット。
* **ログ**：構造化JSON（ingest開始/件数/失敗/重複率/分類分布）。
* **GDPR/著作権**：本文の全文保存は最小化（要約＋メタ＋リンク中心）。

---

## 11. サンプル：MCPサーバーツール（Python/FastMCP）

> 依存：`mcp[cli]`, `psycopg`, `pydantic`

```python
# server.py
from typing import List, Optional, TypedDict
from mcp.server.fastmcp import FastMCP
import psycopg
from datetime import datetime, timezone
import zoneinfo

JST = zoneinfo.ZoneInfo("Asia/Tokyo")
mcp = FastMCP("NewsHub")

class Item(TypedDict):
    title: str
    published_at: str  # ISO 8601 (+09:00)
    genre: str
    url: str
    source: str

def to_jst_iso(ts_utc: datetime) -> str:
    return ts_utc.astimezone(JST).isoformat(timespec="seconds")

@mcp.tool()
def latest_news(limit: int = 50, genres: Optional[List[str]] = None) -> List[Item]:
    sql = """
      SELECT title, url, source, genre, published_at
      FROM items
      WHERE ($1::text[] IS NULL OR genre = ANY($1))
      ORDER BY published_at DESC
      LIMIT $2
    """
    with psycopg.connect() as conn:
        rows = conn.execute(sql, (genres, limit)).fetchall()
    return [
        {
            "title": r[0],
            "url": r[1],
            "source": r[2],
            "genre": r[3] or "general",
            "published_at": to_jst_iso(r[4]),
        }
        for r in rows
    ]

@mcp.resource("news://item/{id}")
def read_item(id: int) -> str:
    with psycopg.connect() as conn:
        r = conn.execute("SELECT raw FROM items WHERE id=%s", (id,)).fetchone()
    return (r[0] or {}) if r else "{}"

if __name__ == "__main__":
    # stdio: `uv run mcp dev server.py` あるいは HTTP でマウント
    mcp.run_stdio()
```

* FastMCPのクイックスタート・構造化出力は公式README参照。 ([GitHub][5])

---

## 12. サンプル：RSSインジェスター（抜粋）

```python
# ingest_rss.py
import feedparser, httpx, psycopg, hashlib, pytz
from dateutil import parser as dtp
from urllib.parse import urlsplit, urlunsplit

FEEDS = [
  "https://www3.nhk.or.jp/rss/news/cat0.xml",
  # ... 任意のRSS/Atom
]

def canon(url: str) -> str:
  s = urlsplit(url)
  return urlunsplit((s.scheme, s.netloc, s.path, "", ""))  # UTM等除去

def to_utc(published_str: str):
  dt = dtp.parse(published_str)
  if not dt.tzinfo: dt = dt.replace(tzinfo=pytz.UTC)
  return dt.astimezone(pytz.UTC)

with psycopg.connect() as conn:
  for feed in FEEDS:
    d = feedparser.parse(feed)
    for e in d.entries:
      url = canon(e.link)
      title = e.title
      pub = to_utc(getattr(e, "published", getattr(e, "updated", "")) or "")
      conn.execute("""
        INSERT INTO items (source, url, title, published_at, first_seen_at, raw)
        VALUES (%s,%s,%s,%s, now(), %s)
        ON CONFLICT (url) DO NOTHING
      """, (feed, url, title, pub, e))
  conn.commit()
```

* RSS/Atom仕様に準拠するデータは`feedparser`で安全に取得可能。 ([RSSアドバイザリーボード][6], [IETF Datatracker][7])

---

## 13. 既定ジャンル（第1層・案）

* `politics`, `economy, business and finance`, `science and technology`, `health`, `arts, culture, entertainment and media`, `sports`, `education`, `environment`, `disaster and accident`, `crime, law and justice`, `lifestyle and leisure`, `religion and belief`, `society`, `weather`, `travel and tourism`, `gaming`, `anime/manga`, `general`
  ※ ベースはIPTC Media Topics（必要に応じて和名併記／階層深掘り）。 ([IPTC][21])

---

## 14. 監視・運用

* **メトリクス**：`ingest_duration_seconds`, `items_ingested_total`, `dup_ratio`, `classify_confidence_avg`
* **アラート**：コネクタ別連続失敗、NewsAPIクォータ閾値、DB遅延
* **ダッシュボード**：ジャンル分布（当日/週）、上位ソース、重複率推移

---

## 15. フェーズ分割（導入順）

1. **MVP**：RSS/Atom＋NewsAPI＋HN → 正規化・重複排除・IPTC第1層でのジャンル付与 → MCP `latest_news/search_news`
2. **検索強化**：PGroonga導入、日本語全文検索・タグファセット
3. **拡張**：GDELT・YouTube/Reddit等の公式APIを段階的に（認可・レート対応）
4. **高度化**：ゼロショット→少量教師で品目別分類器を蒸留

---

### 備考（根拠の一部）

* MCP仕様とSDK（Python/Tools/Resources/HTTP/stdio） ([Model Context Protocol][1], [GitHub][5])
* ニュース取得の標準（RSS/Atom）とNewsAPI/HN/GDELT ([RSSアドバイザリーボード][6], [IETF Datatracker][7], [ニュースAPI][8], [GitHub][9], [HN Search][10], [GDELT Project][11])
* 日本語全文検索：PGroonga（PostgreSQL拡張） ([pgroonga.github.io][14], [PostgreSQL][15])
* 重複検出の代表手法（MinHash/SimHash/オンライン検出） ([Google Research][17], [ACLア Anthology][18])
* ジャンル標準：IPTC Media Topics（多言語・階層型）とゼロショット適用例 ([IPTC][21], [IPTC][28], [Hugging Face][23])

---

