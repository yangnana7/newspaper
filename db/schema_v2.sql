-- v2 データモデル（言語非依存・AI検索前提）

-- 必要拡張（環境に合わせて導入済みであること）
-- CREATE EXTENSION IF NOT EXISTS vector;
-- CREATE EXTENSION IF NOT EXISTS pgroonga; -- 任意

-- 1. Document（原子）
CREATE TABLE IF NOT EXISTS doc (
  doc_id         BIGSERIAL PRIMARY KEY,
  source         TEXT NOT NULL,            -- feed/api 名
  source_uid     TEXT,                     -- 外部ID
  url_canon      TEXT UNIQUE,              -- 正規化URL
  title_raw      TEXT NOT NULL,            -- 原文タイトル
  lang           TEXT,                     -- 自動判定(ja/en/…)
  published_at   TIMESTAMPTZ NOT NULL,     -- UTC保存
  first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  hash_body      BYTEA,                    -- 本文ハッシュ（重複検出）
  raw            JSONB                     -- 生ペイロード（必要時のみ全文）
);
CREATE INDEX IF NOT EXISTS idx_doc_published ON doc (published_at DESC);

-- 2. Chunk（検索の単位；多言語共有空間）
CREATE TABLE IF NOT EXISTS chunk (
  chunk_id   BIGSERIAL PRIMARY KEY,
  doc_id     BIGINT REFERENCES doc(doc_id) ON DELETE CASCADE,
  part_ix    INT NOT NULL,                 -- 0..N（スライディング窓）
  text_raw   TEXT NOT NULL,                -- 原文（未翻訳）
  span       INT4RANGE,                    -- 文字オフセット範囲（任意）
  lang       TEXT,                         -- 検知言語（任意）
  created_at TIMESTAMPTZ DEFAULT now()
);
-- 同一 doc で同じ part_ix は一意
DO $$ BEGIN
  ALTER TABLE chunk ADD CONSTRAINT uq_chunk_doc_part UNIQUE (doc_id, part_ix);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_chunk_doc_part ON chunk (doc_id, part_ix);

-- 3. Vector（モデル可変・空間多層）
--   embedding_space: 例 'bge-m3', 'e5-multilingual', 'laBSE'
CREATE TABLE IF NOT EXISTS chunk_vec (
  chunk_id        BIGINT REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  embedding_space TEXT NOT NULL,
  dim             INT NOT NULL,
  emb             vector NOT NULL,
  PRIMARY KEY (chunk_id, embedding_space)
);
-- 例: HNSW インデックス（pgvector >=0.5）
-- Cos類似を使う場合は vector_cosine_ops へ変更し、エンコード時の normalize と整合させてください。
CREATE INDEX IF NOT EXISTS idx_chunk_vec_hnsw_bge_m3
  ON chunk_vec USING hnsw (emb vector_l2_ops)
  WHERE embedding_space='bge-m3';

-- よく使うヒント/エンティティ参照のための補助インデックス
CREATE INDEX IF NOT EXISTS idx_hint_genre ON hint (doc_id) WHERE key='genre_hint';
CREATE INDEX IF NOT EXISTS idx_entity_ext ON entity (ext_id);

-- 4. Entities（言語非依存のアンカー）
CREATE TABLE IF NOT EXISTS entity (
  ent_id   BIGSERIAL PRIMARY KEY,
  ext_id   TEXT UNIQUE,                    -- 例 'Q95' (YouTube) / 'Q781' (Tokyo)
  kind     TEXT,                           -- person/org/place/event/topic…
  attrs    JSONB                           -- 別名/同義語/軽メタ
);

CREATE TABLE IF NOT EXISTS mention (
  chunk_id BIGINT REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  ent_id   BIGINT REFERENCES entity(ent_id) ON DELETE CASCADE,
  span     INT4RANGE,
  conf     REAL,
  PRIMARY KEY (chunk_id, ent_id, span)
);

-- 5. Events（誰が／何を／いつ／どこで：抽象化）
CREATE TABLE IF NOT EXISTS event (
  event_id    BIGSERIAL PRIMARY KEY,
  type_id     TEXT,                        -- 例: 'medtop:20000233' or 'schema:Event'
  t_start     TIMESTAMPTZ,
  t_end       TIMESTAMPTZ,
  loc_geohash TEXT,                        -- 言語に依らない空間キー
  attrs       JSONB                        -- 追加メタ（数値・ID）
);

CREATE TABLE IF NOT EXISTS event_participant (
  event_id BIGINT REFERENCES event(event_id) ON DELETE CASCADE,
  role     TEXT,                           -- subject/object/agent/target…
  ent_id   BIGINT REFERENCES entity(ent_id),
  PRIMARY KEY (event_id, role, ent_id)
);

CREATE TABLE IF NOT EXISTS evidence (
  event_id BIGINT REFERENCES event(event_id) ON DELETE CASCADE,
  doc_id   BIGINT REFERENCES doc(doc_id) ON DELETE CASCADE,
  chunk_id BIGINT REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  weight   REAL,
  PRIMARY KEY (event_id, doc_id, chunk_id)
);

-- 6. Hints（AI向けの“ヒント”だけ）
CREATE TABLE IF NOT EXISTS hint (
  doc_id  BIGINT REFERENCES doc(doc_id) ON DELETE CASCADE,
  key     TEXT,      -- 'genre_hint','region','market','sports_league' など
  val     TEXT,      -- 値はなるべくID（IPTCコード/ISO/リーグID…）
  conf    REAL,
  PRIMARY KEY (doc_id, key)
);
