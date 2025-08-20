了解。**“AIが自分で引ける” ことに全振り**した、言語非依存・可視化後回しの**AI-ネイティブ検索用データ層**を定義します。可視化や翻訳は最終段でのみ使用。MCPは**純JSONで最小限メタ**＋**言語横断ベクトル**＋**知識グラフ**を返すだけにします。

# 0. 設計ゴール（再定義）

* **言語非依存**：本文は原文のまま保存し、検索は**多言語共有ベクトル空間**＋\*\*ID化された実体（QID等）\*\*で解決。
* **AIファースト**：人間向けUI前提のフィールドは最小化。**LLMが組み合わせて推論**しやすい原子的ストレージ。
* **ミニマム保証**（要件継承）：`title`（原文）/ `published_at`（UTC）/ `genre_hint`（推測可：ID列挙／空でも可）。

---

# 1. データモデル（PostgreSQL + pgvector + PGroonga任意）

## 1.1 Document（原子）

```sql
CREATE TABLE doc (
  doc_id        BIGSERIAL PRIMARY KEY,
  source        TEXT NOT NULL,             -- feed/api 名
  source_uid    TEXT,                      -- 外部ID
  url_canon     TEXT UNIQUE,               -- 正規化URL
  title_raw     TEXT NOT NULL,             -- 原文タイトル
  lang          TEXT,                      -- 自動判定(ja/en/…)
  published_at  TIMESTAMPTZ NOT NULL,      -- UTC保存
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  hash_body     BYTEA,                     -- 本文ハッシュ（重複検出）
  raw           JSONB                      -- 生ペイロード（全文は必要時のみ）
);
CREATE INDEX ON doc (published_at DESC);
```

## 1.2 Chunk（検索の単位；多言語共有空間）

```sql
CREATE TABLE chunk (
  chunk_id   BIGSERIAL PRIMARY KEY,
  doc_id     BIGINT REFERENCES doc(doc_id) ON DELETE CASCADE,
  part_ix    INT NOT NULL,                 -- 0..N（スライディング窓）
  text_raw   TEXT NOT NULL,                -- 原文（トークン化不要）
  span       INT4RANGE,                    -- 文字オフセット範囲
  lang       TEXT,                         -- 検知言語（任意）
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON chunk (doc_id, part_ix);
```

## 1.3 Vector（**モデル可変・空間多層**）

```sql
-- pgvector 拡張前提
-- embedding_space: 例 'bge-m3', 'e5-multilingual', 'laBSE'
CREATE TABLE chunk_vec (
  chunk_id       BIGINT REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  embedding_space TEXT NOT NULL,
  dim            INT NOT NULL,
  emb            vector NOT NULL,
  PRIMARY KEY (chunk_id, embedding_space)
);
-- HNSWインデックス（PostgreSQL16 + pgvector 0.5以降）
CREATE INDEX ON chunk_vec USING hnsw (emb vector_l2_ops) WHERE embedding_space='bge-m3';
```

> これで**言語に依らず**クロスリンガル検索が可能（モデル差し替えも列追加だけ）。

## 1.4 Entities（**言語非依存のアンカー**）

```sql
-- 実体は外部KB IDで固定：Wikidata QID/GeoNames/ISO等
CREATE TABLE entity (
  ent_id    BIGSERIAL PRIMARY KEY,
  ext_id    TEXT UNIQUE,                   -- 例 'Q95' (YouTube) / 'Q781' (Tokyo)
  kind      TEXT,                          -- person/org/place/event/topic…
  attrs     JSONB                          -- 別名/同義語/軽メタ（翻訳は不要）
);

CREATE TABLE mention (
  chunk_id  BIGINT REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  ent_id    BIGINT REFERENCES entity(ent_id) ON DELETE CASCADE,
  span      INT4RANGE,
  conf      REAL,                          -- リンク確信度
  PRIMARY KEY (chunk_id, ent_id, span)
);
```

## 1.5 Events（**誰が／何を／いつ／どこで**：抽象化）

```sql
CREATE TABLE event (
  event_id   BIGSERIAL PRIMARY KEY,
  type_id    TEXT,                         -- 例: 'medtop:20000233' or 'schema:Event'
  t_start    TIMESTAMPTZ,
  t_end      TIMESTAMPTZ,
  loc_geohash TEXT,                        -- 言語に依らない空間キー
  attrs      JSONB                         -- 追加メタ（数値・ID）
);

CREATE TABLE event_participant (
  event_id BIGINT REFERENCES event(event_id) ON DELETE CASCADE,
  role     TEXT,                           -- subject/object/agent/target…
  ent_id   BIGINT REFERENCES entity(ent_id),
  PRIMARY KEY (event_id, role, ent_id)
);

CREATE TABLE evidence (
  event_id  BIGINT REFERENCES event(event_id) ON DELETE CASCADE,
  doc_id    BIGINT REFERENCES doc(doc_id) ON DELETE CASCADE,
  chunk_id  BIGINT REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  weight    REAL,
  PRIMARY KEY (event_id, doc_id, chunk_id)
);
```

## 1.6 Hints（**AI向けの“ヒント”だけ**）

```sql
CREATE TABLE hint (
  doc_id    BIGINT REFERENCES doc(doc_id) ON DELETE CASCADE,
  key       TEXT,      -- 'genre_hint','region','market','sports_league' など
  val       TEXT,      -- 値はなるべくID（IPTCコード/ISO/リーグID…）
  conf      REAL,
  PRIMARY KEY (doc_id, key)
);
```

* `genre_hint` は **英語名ではなくコード**（例：`medtop:04000000`）で保存。可視化時のみ翻訳。

---

# 2. 取り込みパイプライン（言語を“無視”する手順）

1. **正規化**：URL正規化、時間は**必ずUTC**、タイトルは原文。
2. **チャンク化**：トークンでなく**文字数**基準（例 1,200±200 文字、重なり 200）。
3. **埋め込み**：多言語共有空間モデルで**chunk単位**に作成→`chunk_vec`へ。
4. **実体抽出/リンク**：NE/ELでWikidata等の**ID**へ吸着（名前は保存不要）。
5. **イベント抽象化**：SRL/OIEでS-P-O→`event`+`event_participant`+`evidence`。
6. **重複排除**：URL正規化＋**MinHash/SimHash**は**タイトル＋要約**で。多言語は**ベクトル近傍**も併用（翻訳不要）。
7. **ヒント付与（任意）**：供給メタやルールで軽い`hint`のみ設定（欠損OK）。

> **翻訳は一切しない。** 可視化や要約で必要になった時にのみ on-demand 実行。

---

# 3. 検索アルゴリズム（AI向け）

## 3.1 セマンティック検索（クエリ言語自由）

* 入力：`q_text`（任意言語）。
* 手順：
  a) 同じ**embedding\_space**でクエリ埋め込み → `chunk_vec` の HNSW 上位K。
  b) `recency_boost` と `source_weight` を**ランク融合**（BM25は任意）。
  c) 近傍チャンクの `doc_id` を束ね、**evidenceバンドル**を返す。

**スコア例**

```
Score = α·cos_sim + β·recency_decay(Δt) + γ·source_trust + δ·entity_overlap(Q)
```

（係数はA/Bで最適化）

## 3.2 エンティティ・イベント軸

* `entity_search(ext_id[])`：言語不要。
* `event_timeline(ent_id|type_id, time_range)`：**UTC時系列**で返す。
* `similar_events(event_id)`：`evidence.emb` の平均ベクトルで近傍。

---

# 4. MCP I/F（LLMが食べやすい最小JSON）

**tools**

* `semantic_search(q: str, top_k: int=50, since: str|null) -> [Bundle]`
* `entity_search(ext_ids: [str], top_k: int=50) -> [Bundle]`
* `event_timeline(filter: {ext_id?:str,type_id?:str,time?:{from?:str,to?:str}}, top_k:int=200) -> [EventLite[]]`
* `doc_head(doc_id:int) -> {title_raw, published_at, url_canon, hints: {genre?:code}, entities:[ext_id]}`

**返却（Bundle最小形）**

```json
{
  "doc_id": 123,
  "title": "原文タイトル",
  "published_at": "2025-08-19T03:12:00Z",
  "genre_hint": "medtop:04000000",     // なくてもよい
  "evidence": [
    {"chunk_id": 987, "span": [120, 560], "score": 0.83}
  ],
  "entities": ["Q781","Q95"],
  "url": "https://…"
}
```

> LLMは `entities`（QID等）と `evidence.span` を使って**根拠付き回答**を構成できる。

---

# 5. 設定・実装ディテール（Ubuntu前提）

* **DB**：PostgreSQL 16、`CREATE EXTENSION vector;`（pgvector）、`CREATE EXTENSION pgroonga;`（任意）。
* **埋め込み**：`bge-m3` / `e5-multilingual` / `laBSE` のいずれかを**embedding\_space**として並存。
* **言語判定**：CLD3/fastText いずれか。これは単に`lang`記録用。
* **ジョブ**：`systemd` timerで取り込み、別timerで実体リンク・イベント抽象化。
* **監視**：`items_ingested_total / vec_build_latency / recall@k on eval-set` をPrometheusで可視化。

---

# 6. 人間向け可視化を“最後”に行うための最小橋渡し

* **タイトル/時間/（あれば）ジャンル**のみを`doc_head`で返す。
* 表示層はここから**必要時のみ翻訳**（titleは翻訳版を別キーで持たない）。
* ジャンルは**コード→ラベル**変換をUI側で行う（サーバーはコードしか返さない）。

---

# 7. 導入順（短期→中期）

1. **MVP**：Doc/Chunk/Vector を構築 → RSS/NewsAPI/HNから取り込み → `semantic_search` 完成。
2. 実体リンク（Wikidata QID） → `entity_search`/`event_timeline` 解放。
3. 重複排除の多言語対応（MinHash＋ベクトル近傍の二段）。
4. 評価セット作成（クエリ100件×多言語）で **recall\@10**/**nDCG\@10** を追う。

---

## 付録：重複検出の実装ガイド（翻訳不要）

* **ハードキー**：`url_canon` の衝突回避。
* **ソフトキー**：`SimHash(title_raw)` + `MinHash(n-gram of title_raw||summary)`
* **ベクトル**：`cos_sim > τ` かつ `published_at` が近いとき同クラスター。

---

この構成なら、**言語は保存時に一切“開かない”**まま、**AIが使う直前だけ**翻訳・要約・整形を行えます。可視化不要のデータ層としては、**（1）多層ベクトル、（2）ID化された実体、（3）時空間で整列したイベント**の三点を用意しておけば、LLMの探索空間を最小労力で横断できます。

結論から：**十分に現実的**です。ClaudeCode と CodexCLI を“設計の決め打ち＋テスト駆動”で走らせれば、**MVPは 2–3 スプリント相当の人手で到達**できます。難所は「実体リンク（Wikidata QID）」と「イベント抽象化（SRL/OIE）」の精度作り込み。そこだけ人間の評価・微修正が要ります。それ以外（MCP骨格、RSS/NewsAPI/HN連携、pgvector検索、重複排除、systemd運用）は**LLM主導で8〜9割自動化**できます。

---

# 1) コンポーネント別「LLM達成度」マップ

| 項目                            | 具体作業                           |     LLM達成度 | 人手の関与              |
| ----------------------------- | ------------------------------ | ---------: | ------------------ |
| MCPサーバー骨格（FastMCP/stdio/HTTP） | tools/resources 定義、型付け、構成      |  **◎ 95%** | 仕様だけ固めれば自動生成で通る    |
| 取込: RSS/Atom                  | feedparser, UTC化, 正規化          | **◎ 100%** | なし（フィードURL列挙のみ）    |
| 取込: NewsAPI / HN              | 認証、レート制御、再試行                   |  **◎ 95%** | APIキー投入と上限設計は人間    |
| 正規化スキーマ                       | doc/chunk/chunk\_vec/hint のDDL |  **◎ 95%** | 初回レビューのみ           |
| ベクトル検索(pgvector)              | HNSW索引、近傍検索、再ランク               |  **○ 90%** | チューニング係数はA/Bで人間が決定 |
| 重複排除                          | URL正規化＋MinHash/SimHash         |  **○ 90%** | 閾値τの決定と例外ルール       |
| 言語依存排除のチャンク化                  | 文字長スライディング窓                    |  **◎ 95%** | 方針どおり生成でOK         |
| 実体リンク（Wikidata QID）           | NER+EL、別名辞書、曖昧性解消              |  **△ 70%** | 評価セット作成・誤リンク修正が必要  |
| イベント抽象化（SRL/OIE）              | S-P-O抽出→event表へ                |  **△ 60%** | ルール補強と誤抽出の抑制       |
| ランク融合                         | cos類似×新鮮度×信頼度                  |  **○ 85%** | 係数最適化（グリッド/A/B）    |
| systemd 運用                    | service/timer/環境変数             | **◎ 100%** | サーバ事情に合わせるだけ       |
| 監視                            | Prometheus Exporter, Grafana   |  **○ 80%** | 観点設計（SLO/アラート閾値）   |
| セキュリティ                        | .env/Secrets, トークン検証           |  **△ 70%** | 秘密管理の方針は人間が決める     |

> 目安：**MVP到達の工数の 70–80% を LLMに肩代わり**させられます。難所2点は“評価→微修正ループ”を必ず人間が回す。

---

# 2) 「LLMが強い領域」と「人間がやるべき領域」

**LLMが得意**

* 既知パターンのコード生成：FastAPI/FastMCP、psycopg、pgvector/HNSW、feedparser、NewsAPI/HNコネクタ、重複検出実装、CI、systemdユニット。
* スキーマ間のデータ搬送・ETLのボイラープレート化。
* テストコード雛形（pytest, hypothesis, factory boy）生成。

**人間が決め打つべき**

* **評価指標**：`recall@10` / `nDCG@10` / `dup_ratio` / `entity_link_acc` の“基準値”。
* **閾値と係数**：MinHash/SimHashのτ、ランク融合の係数 αβγδ、recency decay の半減期。
* **秘匿事項**：APIキー、ニュースソース選定（TOS/商用可否）、監視のSLO。

---

# 3) ClaudeCode / CodexCLI の使い分け（実務パターン）

* **ClaudeCode**：大規模改変の設計・分割・レビュー、PR説明、仕様→テスト→実装の一連化が得意。
* **CodexCLI**：手元での**反復的コード生成・修正**に向く（関数単位の差分生成、即時テスト実行）。

**推奨運用**

1. 要件→**タスク分割PRD**をClaudeに作らせる（ファイル/差分単位で指示）。
2. 各タスクを**CodexCLIで局所実装**→pytest実行→失敗ログをそのまま餌に再修正。
3. まとまった変更はClaudeに**PR本文・設計ノート**を書かせる。

---

# 4) そのまま貼って使える「指示テンプレ」（抜粋）

**A. スキーマ＋マイグレーション（ClaudeCode向け）**

```
目的: 言語非依存のAIネイティブ検索層を作る
要件: PostgreSQL16 + pgvector。doc/chunk/chunk_vec/hint のDDLとマイグレーション
制約: published_atはUTC, urlはcanonical一意, chunkは文字長1200±200/overlap200
成果物: 
- sql/001_init.sql（DDL一式）
- app/db.py（psycopg接続とmigrations runner）
- tests/test_schema.py（NOT NULL/PK/FK/UNIQUE検証）
```

**B. ベクトル近傍検索（CodexCLI向け）**

```
実装: pgvector HNSW で cosine近傍を返す search_chunks(q_text, top_k)
前提: embedding_space='bge-m3' を既存列に使用
要件: 
- クエリ埋め込み→SQLで近傍K取得→doc束ね→再ランク
- 再ランク Score = 0.7*cos + 0.2*recency_decay + 0.1*source_trust
- 単体テスト: tests/test_search.py に recall@10 >= 0.6（evalセット同梱）
```

**C. 重複排除（CodexCLI向け）**

```
実装: normalize_url, title_simhash(title_raw), minhash_ngrams(title+summary)
条件: (simhash_hamming<=4 or jaccard>=0.8) かつ |Δt|<=48h → 同クラスタ
副作用: items.dup_cluster_id 付与
テスト: 近似重複データで dup_ratio を 15–35% に収める
```

**D. 実体リンク（ClaudeCode向け）**

```
目的: chunk→entity(QID) リンク
要件:
- spaCy/Trankit等NER→BLINK/Bootleg/Elasticsearch辞書でEL
- 競合時はprior(source_country, pageview等)でtie-break
- 出力: mention(chunk_id, ent_id, span, conf) 0.0–1.0
- テスト: gold 200例で link_acc >= 0.8 を暫定基準
```

**E. MCPツール公開**

```
実装: tools.semantic_search / tools.entity_search / resources.news://item/{id}
出力: title_raw, published_at(ISO), genre_hint(code), entities(QIDs), evidence spans
テスト: JSON Schema整合、空結果/エラー時のHTTP 4xx/5xx
```

---

# 5) テスト & 受入（人間のレバー）

* **ゴール指標（MVP）**

  * 取込安定度：主要3ソースで 24h 無停止 / 欠測 < 1%
  * 検索品質：`recall@10 ≥ 0.60`（社内100クエリ多言語）
  * 重複排除：`dup_ratio 15–35%`（クラスタリング率の健全範囲）
  * 実体リンク：`link_acc ≥ 0.80（200例）`
* **DoD（Definition of Done）**

  * すべてのtools/resourcesに**スキーマ付**
  * systemd timer で 10分間隔 ingest / 失敗は再試行＋通知
  * Prometheus に `items_ingested_total / vec_build_latency / dup_ratio` を輸出

---

# 6) リスクと対策（LLM依存ゆえの落とし穴）

* **埋め込みモデル管理**：ローカル常駐 or API依存。
  ⇒ *方針*：まずAPI（運用簡単）→後でローカル化（CPU/GPU）に差し替え。`embedding_space`で多層共存できる設計済。
* **EL/イベント抽象の精度**：言語やニュースドメインで崩れる。
  ⇒ *方針*：評価セットを最初に用意し、**失敗例をClaudeに与えてルール生成**。
* **Secrets/レート制限**：LLMがコードに直書きしがち。
  ⇒ *方針*：.env必須、`secrets.py` 生成禁止のガードレールを最初に明記。
* **規約順守**：非公式スクレイピングの誘惑。
  ⇒ *方針*：RSS/公式API優先。TOSチェックは人間レビュー。

---

# 7) 現実的な“最短ルート”

* **スプリント1**：DDL/DB接続、RSS取込、ベクトル検索、MCP `semantic_search`。
* **スプリント2**：重複排除、NewsAPI/HN、rank融合、systemd/監視。
* **スプリント3**：実体リンクの精度作り込み、イベント抽象（最低限）、評価セット整備。

> ここまで、**コーディングは概ねLLM相棒で完走**できます。人間の主仕事は“基準作り・閾値決定・例外審査”。

---

**要するに**：この設計は**LLM実装に相性が良い**（スキーマ固定・I/O明確・テスト基準化が容易）。
ClaudeCode は**設計～PR駆動**、CodexCLI は**局所修正＆テスト反復**で回すと生産性が高い。
ネックは **QIDリンクとイベント抽象の品質**だけ—ここは**小さな評価セット**を先に作って、LLMに“失敗を学ばせる”運用で突破できます。
