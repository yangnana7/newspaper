-- 取り込み件数（日次）
SELECT date_trunc('day', first_seen_at) AS day, count(*) AS items
FROM doc
GROUP BY 1
ORDER BY 1 DESC
LIMIT 30;

-- ベクトル未生成チャンク数
SELECT count(*) AS chunks_pending
FROM chunk c
LEFT JOIN chunk_vec v ON (v.chunk_id=c.chunk_id)
WHERE v.chunk_id IS NULL;

-- ベクトル次元・space別の件数
SELECT embedding_space, dim, count(*)
FROM chunk_vec
GROUP BY 1,2
ORDER BY 1,2;

