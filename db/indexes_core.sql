-- pgvector HNSW index for semantic search acceleration
-- Requires pgvector 0.5+ and PostgreSQL 16+
CREATE INDEX IF NOT EXISTS ix_chunk_vec_bge_m3_hnsw
ON chunk_vec USING hnsw (emb vector_cosine_ops)
WHERE embedding_space='bge-m3';

