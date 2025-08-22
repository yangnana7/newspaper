-- Optional but recommended indexes for web/API performance
-- Safe to run multiple times.

-- Recent-first listing
CREATE INDEX IF NOT EXISTS idx_doc_published_at_desc ON doc (published_at DESC);

-- Source filter
CREATE INDEX IF NOT EXISTS idx_doc_source ON doc (source);

-- De-dup by canonical URL (and recency)
CREATE INDEX IF NOT EXISTS idx_doc_urlcanon_published_at_desc ON doc (url_canon, published_at DESC);

-- Hints by (doc_id, key)
CREATE INDEX IF NOT EXISTS idx_hint_docid_key ON hint (doc_id, key);

-- Fast ILIKE for titles (requires pg_trgm)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_doc_title_raw_trgm ON doc USING GIN (title_raw gin_trgm_ops);

