-- HNSW index for cosine on embedding_space = 'bge-m3'
CREATE INDEX IF NOT EXISTS hnsw_chunk_vec_bgem3_cos
ON chunk_vec
USING hnsw (emb vector_cosine_ops)
WHERE embedding_space = 'bge-m3';