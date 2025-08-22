=== Ubuntu Work Report ===

## 1. Schema and Index Application Log

### Schema v2.sql - Already Applied
 to_regclass | to_regclass | to_regclass 
-------------+-------------+-------------
 doc         | chunk       | chunk_vec
(1 row)


### Indexes Core - Already Applied
             indexname              
------------------------------------
 chunk_vec_pkey
 doc_pkey
 doc_url_canon_key
 hint_pkey
 idx_chunk_vec_hnsw_bge_m3
 idx_chunk_vec_hnsw_bge_m3_cos
 idx_doc_published
 idx_doc_published_at_desc
 idx_doc_source
 idx_doc_title_raw_trgm
 idx_doc_url
 idx_doc_urlcanon_published_at_desc
 idx_hint_genre
 idx_hint_key
(14 rows)


## 2. API Response Examples

### /api/latest Response:
[
  {
    "doc_id": 121,
    "title": "Hello World",
    "published_at": "2025-08-22T12:36:06+09:00",
    "genre_hint": "news",
    "url": "https://example.com/1",
    "source": "test://local"
  },
  {
    "doc_id": 37,
    "title": "Rockets beat Invincibles to keep slim hopes alive",
    "published_at": "2025-08-22T01:34:07+09:00",
    "genre_hint": "medtop:04000000",
    "url": "https://www.bbc.com/sport/cricket/articles/c4gl8pyjvdxo?at_medium=RSS&at_campaign=rss",
    "source": "BBC News"
  }
]

### /api/search Response:
[
  {
    "doc_id": 121,
    "title": "Hello World",
    "published_at": "2025-08-22T12:36:06+09:00",
    "genre_hint": "news",
    "url": "https://example.com/1",
    "source": "test://local"
  }
]

### /api/search_sem Response (no query - fallback):
[
  {
    "doc_id": 121,
    "title": "Hello World",
    "published_at": "2025-08-22T12:36:06+09:00",
    "genre_hint": "news",
    "url": "https://example.com/1",
    "source": "test://local"
  },
  {
    "doc_id": 37,
    "title": "Rockets beat Invincibles to keep slim hopes alive",
    "published_at": "2025-08-22T01:34:07+09:00",
    "genre_hint": "medtop:04000000",
    "url": "https://www.bbc.com/sport/cricket/articles/c4gl8pyjvdxo?at_medium=RSS&at_campaign=rss",
    "source": "BBC News"
  }
]

## 3. Database Statistics

### Document Count:
 total_docs 
------------
        121
(1 row)


### Embedding Status:
 embedding_space | vector_count 
-----------------+--------------
 bge-m3          |            1
(1 row)


## 4. System Status

### HTTP Application Status:
- Server running on 127.0.0.1:3011 ✓
- Process ID: 41431
41453
48207

### PostgreSQL Status:
- PostgreSQL service: active
- Database: newshub ✓
- Extensions: vector, pg_trgm ✓
