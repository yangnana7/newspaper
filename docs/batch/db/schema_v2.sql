-- schema_v2.sql — AIネイティブ検索用の最小スキーマ
-- NOTE: pgvectorが必要。インストール済みでなければ CREATE EXTENSION vector; は失敗します.

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- ===== Documents =====
CREATE TABLE IF NOT EXISTS doc (
  doc_id        BIGSERIAL PRIMARY KEY,
  source        TEXT NOT NULL,
  source_uid    TEXT,
  url_canon     TEXT UNIQUE,
  title_raw     TEXT NOT NULL,
  author        TEXT,
  lang          TEXT,
  published_at  TIMESTAMPTZ NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  hash_body     BYTEA,
  raw           JSONB
);

CREATE INDEX IF NOT EXISTS idx_doc_published ON doc (published_at DESC);

-- ===== Chunks =====
CREATE TABLE IF NOT EXISTS chunk (
  chunk_id   BIGSERIAL PRIMARY KEY,
  doc_id     BIGINT REFERENCES doc(doc_id) ON DELETE CASCADE,
  part_ix    INT NOT NULL,
  text_raw   TEXT NOT NULL,
  span       INT4RANGE,
  lang       TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunk_doc_part ON chunk (doc_id, part_ix);

-- ===== Embeddings (pgvector) =====
CREATE TABLE IF NOT EXISTS chunk_vec (
  chunk_id        BIGINT REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  embedding_space TEXT NOT NULL,
  dim             INT NOT NULL,
  emb             VECTOR NOT NULL,
  PRIMARY KEY (chunk_id, embedding_space)
);

-- HNSW index (L2). If you use cosine, switch to vector_cosine_ops.
CREATE INDEX IF NOT EXISTS idx_chunk_vec_hnsw_bge_m3
  ON chunk_vec USING hnsw (emb vector_l2_ops)
  WHERE embedding_space = 'bge-m3';

-- ===== Hints (lightweight metadata) =====
CREATE TABLE IF NOT EXISTS hint (
  doc_id  BIGINT REFERENCES doc(doc_id) ON DELETE CASCADE,
  key     TEXT,
  val     TEXT,
  conf    REAL,
  PRIMARY KEY (doc_id, key)
);

CREATE INDEX IF NOT EXISTS idx_hint_genre ON hint (doc_id) WHERE key = 'genre_hint';

-- ===== Entities (optional, for later) =====
CREATE TABLE IF NOT EXISTS entity (
  ent_id  BIGSERIAL PRIMARY KEY,
  ext_id  TEXT UNIQUE,
  kind    TEXT,
  attrs   JSONB
);

CREATE INDEX IF NOT EXISTS idx_entity_ext ON entity (ext_id);

CREATE TABLE IF NOT EXISTS mention (
  chunk_id  BIGINT REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  ent_id    BIGINT REFERENCES entity(ent_id) ON DELETE CASCADE,
  span      INT4RANGE,
  conf      REAL,
  PRIMARY KEY (chunk_id, ent_id, span)
);

-- ===== Events (optional, for later) =====
CREATE TABLE IF NOT EXISTS event (
  event_id    BIGSERIAL PRIMARY KEY,
  type_id     TEXT,
  t_start     TIMESTAMPTZ,
  t_end       TIMESTAMPTZ,
  loc_geohash TEXT,
  attrs       JSONB
);

CREATE TABLE IF NOT EXISTS event_participant (
  event_id BIGINT REFERENCES event(event_id) ON DELETE CASCADE,
  role     TEXT,
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
