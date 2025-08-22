# 運用メモ（Ranking/Env/Feeds）

本メモは Day3 の変更点（ランク融合・環境変数・フィード設定）を抜粋でまとめたものです。

**Ranking（/api/search_sem）**
- 加重: `Score = α*cos + β*recency + γ*source_trust`
- 既定: `RANK_ALPHA=0.7`, `RANK_BETA=0.2`, `RANK_GAMMA=0.1`
- 半減期: `RECENCY_HALFLIFE_HOURS`（例: 24）
- 信頼度: `SOURCE_TRUST_JSON`（例: `{ "NHK 総合": 1.1, "BBC News": 1.0 }`）/ 既定 `SOURCE_TRUST_DEFAULT=1.0`
- 空間: `EMBED_SPACE` または `EMBEDDING_SPACE`（例: `bge-m3`）

**Feeds（config/feeds.sample.json）**
- 例: NHK/BBC/ITmedia/GIGAZINE/毎日新聞/Yahoo!ニュース テック
- `scripts/ingest_rss.py --feeds config/feeds.sample.json` で投入
- 重複は `url_canon` と `hash_body` で緩和（要スキーマ）

**注意**
- ベクトル: `chunk_vec.emb = vector(768)`、cosine `<=>`
- 新規DBやCIでは `db/schema_v2.sql` → `db/indexes_core.sql` を適用
- q未指定の `/api/search_sem` は新着順フォールバック

