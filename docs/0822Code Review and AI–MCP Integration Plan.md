Code Review and AI–MCP Integration Plan
1 Repository Overview and Current State

The newspaper repository targets an AI‑oriented news aggregation pipeline. At its core it provides:

Data model (db/schema_v2.sql) – defines a document‑centric schema with tables for documents, chunks, vector embeddings, entities, events and hints. Documents hold basic metadata and raw payload; chunks index segments of text; vector embeddings capture semantic information in a specified space (e.g., bge‑m3) using the vector(768) type and support both L2 and cosine HNSW indexes
GitHub
. Entities, mentions and events provide hooks for knowledge extraction, with event‐evidence linking via a many‑to‑many table.

Ingestion scripts – scripts/ingest_rss.py reads RSS/Atom feeds and populates the doc and chunk tables. It canonicalises URLs to avoid duplicates, stores language and author when available, and upserts hints like genre_hint
GitHub
. Similar scripts exist for NewsAPI and Hacker News. Ingestion is decoupled from embedding and server execution via systemd services and timers.

Embedding script – scripts/embed_chunks.py loads a SentenceTransformer model, fetches un‑embedded chunks, encodes them with optional normalisation, and writes the results into chunk_vec
GitHub
. The script registers pgvector for psycopg and ensures timezone consistency.

Stubs for entity and event extraction – scripts/entity_link_stub.py implements a placeholder entity linker that tokenises simple English words and writes token IDs to the entity and mention tables
GitHub
. scripts/event_extract_stub.py produces dummy events for chunks without evidence
GitHub
. These are minimal but provide integration points for later NLP modules.

MCP server – mcp_news/server.py wraps the FastMCP framework and exposes tools (doc_head, semantic_search, entity_search, event_timeline). It lazily loads a SentenceTransformer based on ENABLE_SERVER_EMBEDDING. Semantic search first tries vector search using <=> (cosine distance) and falls back to recency when embeddings are missing
GitHub
. Results are normalised into a Bundle typed dict. Event timeline queries allow filtering by entity ID, type or time range
GitHub
.

Systemd deployment – deploy/* includes service and timer units for ingestion and embedding, with environment variables in /etc/default/mcp-news controlling DB and API keys. The Day 1 report describes an Ubuntu‑based deployment and emphasises PGVector, systemd timers and CI checks
GitHub
.

Documentation and CI – the repository contains detailed reports explaining design decisions (e.g., migrating to cosine distance and HNSW indexes
GitHub
) and notes the need to adjust dimension when changing models
GitHub
. Tests cover the stub functions. Continuous integration installs dependencies, applies the schema and runs the test suite.

2 Code Review and Observations
2.1 Schema

The doc table normalises articles by canonical URL and stores both the raw payload and a pre‑computed body hash for duplicate detection
GitHub
. Indexes on published_at and url_canon are already present, but adding a composite index on (source,published_at DESC) would speed up per‑source queries.

Vector embeddings are stored in chunk_vec.emb with a fixed dimension of 768 and HNSW indexes for both L2 and cosine distance
GitHub
. This design supports efficient approximate nearest neighbour search but requires re‑indexing if switching models with different embedding sizes.

Entities and events are kept simple; event times and geohashes are nullable to allow stub extraction. The hint table stores lightweight metadata such as IPTC genre codes. Additional indexes on hint (key) and hint (doc_id) are present
GitHub
 to speed up lookups.

2.2 Ingestion and Embedding Scripts

The RSS ingester normalises URLs and gracefully handles date parsing errors by falling back to the current time
GitHub
. It uses upsert semantics to avoid duplicates based on url_canon. However, it updates only the title on conflict; other fields such as raw or author might differ on subsequent runs and should also be considered for updating.

Ingested documents are broken into a single chunk containing the summary or title. This simplifies embedding but limits recall when searching full articles. Future iterations could add content extraction (e.g., boilerplate removal) and tokenise long articles into multiple overlapping windows to improve semantic retrieval.

The embedding script encodes small batches and writes them in a single transaction. It registers the vector extension for psycopg and normalises embeddings for cosine compatibility. This is efficient, but error handling could be improved by logging exceptions and continuing rather than exiting silently.

2.3 MCP Server

The FastMCP wrapper exposes tools for retrieving document heads and performing semantic search. The semantic_search function first attempts an embedding‑based query using <=> and falls back to recency ordering when embeddings are missing
GitHub
. It checks the ENABLE_SERVER_EMBEDDING environment variable to control whether the model is loaded and uses pgvector.psycopg.Vector to ensure type matching
GitHub
. This design gracefully handles missing models or vector indexes.

event_timeline builds flexible SQL conditions based on optional filters (type_id, ext_id, time range) and returns events with ISO‑formatted timestamps
GitHub
. For large datasets, pagination parameters (limit/offset) could be added.

The server file uses typing_extensions.TypedDict to maintain compatibility with Pydantic under Python 3.11
GitHub
.

2.4 Stub Modules

The entity linker stub tokenises capitalised alphanumeric words and treats them as generic tokens
GitHub
. It upserts these into the entity table with a tok: prefix and writes mentions with a fixed confidence of 0.1
GitHub
. This demonstrates the pipeline but offers no real NER capability; integration of a proper multilingual NER (spaCy, Stanza or SudachiPy) and candidate generation via Wikidata/Geonames APIs is planned.

The event extraction stub simply creates an event for every unprocessed chunk and links evidence
GitHub
. While sufficient for testing the event schema, it yields meaningless events. A true event extractor would require relation extraction and temporal normalisation (e.g., SRL/OIE plus Heideltime or SUTime) and maybe geocoding.

2.5 Web UI (Temporary)

The minimal FastAPI/Jinja interface added in your last patch provides an HTML list of recent documents, search by ILIKE, filters and pagination. This UI is deliberately simple and can be discarded or kept for internal testing. More robust user‑facing interfaces should likely live in a separate repository or Next.js frontend and query the MCP server via HTTP.

3 Analysis and Recommendations for Completion
3.1 Finish the AI‑Native Pipeline

The long‑term goal is an AI system that can retrieve relevant news from the MCP server and perform deeper analysis (summarisation, trend detection, question answering). To reach this goal:

Improve content ingestion – move beyond summaries: implement content extraction (e.g., readability-lxml or newspaper3k) and split long articles into multiple chunks (e.g., 512‑token windows with overlap). This will increase recall for semantic search and provide richer context for downstream models.

Entity linking and event extraction – replace the stubs with real NLP components. Suggested pipeline:

Use a multilingual NER library (spaCy with Japanese models, Stanza or SudachiPy) to extract named entities from each chunk.

Query Wikidata or other KBs to map entity strings to ext_id using candidate selection and ranking (e.g., using BM25 over alias tables). Cache results to reduce API calls.

For event extraction, adopt either a template‑based approach (detecting “X said Y”, “A bought B”) or an open information extraction model. Use tools like PropBank/Semantic Role Labelling or custom BERT classifiers to identify event type and participants.

Normalise times using a temporal tagger and generate geohashes from place names.

Semantic search and ranking fusion – the repository already supports vector search using PGVector’s <=> operator and falling back to recency. The next step is to combine multiple signals: lexical matching (e.g., PGTrgm or BM25), semantic similarity, recency, source reliability and user preferences. A simple linear combination of normalised scores can be implemented in SQL or Python, with weights tuned on a held‑out set. For Japanese search, PGroonga or Meilisearch could improve morphological indexing.

AI orchestration – implement an application layer where an LLM can call MCP tools autonomously. For example, use a LangChain or FastMCP agent that decides whether to call semantic_search, entity_search or event_timeline based on the query and then summarises the returned articles. The server already defines these tools, so the agent can be built on top of them. Caching and rate limiting should be added to avoid expensive embedding re‑computations.

Monitoring and evaluation – integrate Prometheus metrics for ingestion lag, embedding throughput and search latency. Develop an evaluation script that computes recall/nDCG on a curated question set with ground‑truth relevant documents (e.g., the eval_recall_stub.py hints at this). Use these metrics to guide model selection and ranking weights.

3.2 Customising News Sources and Feeds

Flexible feed configuration – define a declarative feeds.json where each entry includes URL, human‑readable name, genre code, language, and optional extraction rules (CSS selectors for content extraction). Provide CLI flags or environment variables to override per‑run options such as maximum entries and categories.

Adding new sources – to support paywalled or proprietary feeds, implement connectors that call APIs (e.g., NewsAPI, GDELT, custom R&D feeds) or scrape websites ethically. Each connector should normalise output into the doc/chunk model and register its own systemd service and timer.

Per‑source weighting and filtering – store per‑source reliability or priority weights in a source_meta table. Use these weights in ranking fusion and allow excluding low‑quality sources at query time. Genre hints could also be enriched via IPTC or custom taxonomies.

3.3 Integration Plan and Timeline

A rough roadmap with estimated effort (assuming one engineer with NLP/ML skills):

  Phase | Tasks | Est. Duration
  --- | --- | ---
  Phase 1 (1–2 weeks) | Productionise ingestion: add full‑text extraction for articles; refactor ingestion scripts into reusable modules; implement feed configuration file; add indexes (source,published_at) and trigram search for titles; remove the temporary FastAPI UI or replace it with a command‑line tool for sampling documents. | 1 week
   | Semantic search tuning: evaluate different SentenceTransformer models (e.g., multilingual E5 vs. BGE) and adjust embedding dimension. Implement a ranking fusion prototype combining vector similarity and recency/source weighting. | 1 week
  Phase 2 (2–3 weeks) | Entity linking: integrate an NER library and candidate selection from Wikidata/Geonames; store entity attributes (language‑agnostic names, categories). Evaluate precision on a small labeled set. | 1.5 weeks
   | Event extraction: adopt an open information extraction or template‑based model to detect events (e.g., purchases, elections). Design an event schema aligned with schema.org or IPTC and populate event participants. | 1.5 weeks
  Phase 3 (1–2 weeks) | AI agent integration: build a LangChain or FastMCP agent that can call MCP tools, summarise results and answer user questions. Provide a simple API endpoint for the agent. Add caching and rate limiting. | 1 week
   | Monitoring and evaluation: instrument ingestion/embedding processes with Prometheus; implement a test harness for recall/nDCG evaluation; tune ranking weights based on feedback. | 1 week
  Ongoing | Source expansion and customisation: continuously add new feeds and adjust weights; maintain connectors and handle API changes. Perform periodic data cleaning (duplicate detection, outdated news removal). | continuous

4 Conclusion

The repository already lays a strong foundation for an AI‑native news aggregator: a structured database schema, ingestion and embedding scripts, a semantic search server and systemd deployment scripts. To realise the vision of AI‑driven news analysis, the next steps involve enhancing content extraction, implementing real entity and event extraction, improving search ranking and building an agent that can autonomously call MCP tools. Additionally, customising and weighting news sources will ensure better recall and user satisfaction. Following the proposed roadmap will help transform the current prototype into a robust platform where AI can access, analyse and summarise news in multiple languages.

日本語版

# コードレビュー & AI連携計画（翻訳版）

## 1. 現状レビューのまとめ

### 全体像

* **DBスキーマ**は `doc / chunk / chunk_vec / entity / event / hint` に分離済み。AI検索に最適。
* **サーバー側**は `mcp_news/server.py` にて `semantic_search` と `doc_head` がMCP経由で利用可能。
* **CI**はGitHub ActionsでPostgres(pgvector入り)を起動→スキーマ適用→pytestまで一連で通る。
* **スタブ**（`entity_link_stub.py`, `event_extract_stub.py`）が形だけ存在し、ダミー動作は確認済み。

### 改善ポイント

* ファイルに残っていた `...` や未完成コードは修正済みだが、依然として **Event/Entity実装は空**。
* **距離関数の整合性**：ベクトルはcos正規化、DBはL2オペレータ、どちらかに統一必須。
* **インデックス不足**：`doc.url_canon` や `hint.key` など、典型的に使う列に索引追加推奨。
* **UI**は確認用に最小限だけ。削除も可。

---

## 2. 設計方針（Ubuntu用 v2案より）

* **言語非依存・AIファースト**：本文は原文保存、検索は多言語共有ベクトル空間＋ID化されたエンティティで解決。
* **MCPは最小JSON**を返すのみ（`title/published_at/genre_hint/url`、必要ならentity QID）。
* **翻訳やUI向け整形は最後**。保存時には翻訳を一切しない。

### パイプライン

1. RSS/NewsAPI/HN ingest → UTC・URL正規化
2. チャンク化（1200±200文字、オーバーラップ200）
3. ベクトル化（埋め込み空間ごとにHNSW索引）
4. 実体リンク（Wikidata QIDなど）
5. イベント抽象化（誰が／何を／いつ／どこで）
6. 重複排除（URL＋SimHash＋ベクトル近傍）
7. MCP経由で検索応答

---

## 3. 次のステップ（スケジュール案）

### スプリント1（MVP完成）

* RSS取込 → 埋め込み → MCP `semantic_search`
* Recency fallback確認（ENABLE\_SERVER\_EMBEDDING=0で新着順）
* `idx_doc_url`, `idx_hint_key` など汎用インデックス追加

### スプリント2（検索品質向上）

* NewsAPI/HN ingest復旧
* ランク融合（cos類似 × 新鮮度 × ソース信頼度）
* systemd + Prometheusで監視指標収集（ingest件数、vec遅延、recall\@k）

### スプリント3（AIネイティブ化）

* 実体リンク（NER+EL→QID）
* イベント抽象化（SPO→event表）
* 近重複検知（MinHash + Vec近傍）
* `entity_search` / `event_timeline` をMCPに公開

---

## 4. ニュースソース追加・カスタマイズ案

* **公式RSSとAPI優先**（NewsAPI, HN, 各社RSS）
* **日本語ローカル媒体RSS**を追加（共同通信, 日経, NHK, 地域紙）
* **特殊ジャンル**（スポーツリーグ公式, 金融庁発表, 気象庁速報など）を `genre_hint` と組み合わせて拡張
* **信頼度重み付け**（ソース別に係数設定）

---

## 5. AIとMCPサーバーの連携構想

* **AIエージェント**はMCPのtoolsを直接呼び出す：

  * `semantic_search`: 任意言語クエリに対し多言語検索
  * `entity_search`: QID指定でニュース束取得
  * `event_timeline`: 期間＋エンティティ指定で時系列返却
* **返却JSON**はすべてAIが再構成できる形に設計済み（title, url, entities, evidence span）
* **最終的にAIが回答生成**する際、evidenceとしてMCPからの根拠を引用可能にする。

---

## 6. 今後のレポートまとめ

* **現状**：MVP手前（RSS ingest→埋め込み→検索が通る）。UIは暫定。
* **次の到達点**：スプリント1で「AIが自分でニュースを検索できる」状態に。
* **中期ゴール**：スプリント3で「AIがエンティティ・イベント単位でニュースを要約・分析できる」基盤完成。
* **長期ゴール**：カスタムソース・ランキング最適化・評価指標運用まで組み込み、実用水準のAIニュース集約。

---

👉 この翻訳版をベースに、**Day3以降の進行管理レポート**として「MVP達成（スプリント1）」までのタスクを固めるのが次アクションです。

次に、私からは **実際のpatch計画（差分ファイル）** を用意し、`schema_v2.sql`や`server.py`のインデックス追加・距離関数統一・テスト更新を提示するのが良いと思います。