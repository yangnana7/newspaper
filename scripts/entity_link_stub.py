#!/usr/bin/env python3
"""
Entity Linking stub.

方針:
- chunk.text_raw から固有表現抽出 → 候補生成（Wikidata, GeoNames 等）
- 候補スコアリング → ext_id（例: 'Q95'）へ正規化、mention に確信度付きで保存

TODO:
- 軽量NLPの選定（例: spaCy + ja_core_news_md / Stanza / SudachiPy+NE）
- 候補検索: Wikidata API / 事前ダンプ + Elastic/Meilisearch
- キャッシュ・レート制御
"""
import os
import re
import json
from typing import Iterable, List, Tuple

import psycopg


def extract_terms(text: str, max_terms: int = 12) -> List[Tuple[str, int, int, str]]:
    """Token extractor for stub implementation (multilingual-ish).

    Yields (token, start, end, kind) where kind in {"token","surface","hashtag"}.
    - English-like tokens: [A-Za-z][A-Za-z0-9_-]{2,}
    - Katakana surfaces: [\u30A0-\u30FF]{2,}
    - Hashtags: #[A-Za-z0-9_]{2,}
    """
    if not text:
        return []
    pat_en = re.compile(r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b")
    pat_kata = re.compile(r"[\u30A0-\u30FF]{2,}")
    pat_hash = re.compile(r"#[A-Za-z0-9_]{2,}")
    seen = set()
    out: List[Tuple[str, int, int, str]] = []
    for m in pat_en.finditer(text):
        tok = m.group(0)
        key = ("en:") + tok.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((tok, m.start(), m.end(), "token"))
        if len(out) >= max_terms:
            return out
    for m in pat_kata.finditer(text):
        tok = m.group(0)
        key = ("ka:") + tok
        if key in seen:
            continue
        seen.add(key)
        out.append((tok, m.start(), m.end(), "surface"))
        if len(out) >= max_terms:
            return out
    for m in pat_hash.finditer(text):
        tok = m.group(0)
        key = ("hx:") + tok.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((tok, m.start(), m.end(), "hashtag"))
        if len(out) >= max_terms:
            return out
    return out


def upsert_entity(conn: psycopg.Connection, ext_id: str, kind: str = "token", attrs: dict | None = None) -> int:
    cur = conn.execute(
        """
        INSERT INTO entity (ext_id, kind, attrs)
        VALUES (%s, %s, %s)
        ON CONFLICT (ext_id) DO NOTHING
        RETURNING ent_id
        """,
        (ext_id, kind, json.dumps(attrs or {})),
    )
    row = cur.fetchone()
    if row:
        return int(row[0])
    # already existed
    row2 = conn.execute("SELECT ent_id FROM entity WHERE ext_id=%s", (ext_id,)).fetchone()
    return int(row2[0]) if row2 else -1


def process_chunks(conn: psycopg.Connection, limit: int = 100) -> int:
    sql = (
        """
        SELECT c.chunk_id, c.text_raw
        FROM chunk c
        LEFT JOIN mention m ON m.chunk_id = c.chunk_id
        WHERE m.chunk_id IS NULL
        ORDER BY c.chunk_id ASC
        LIMIT %s
        """
    )
    rows = list(conn.execute(sql, (limit,)))
    inserted = 0
    for cid, text in rows:
        terms = extract_terms(text or "")
        if not terms:
            continue
        with conn.transaction():
            for tok, s, e, kind in terms:
                if kind == "token":
                    ext = f"tok:{tok.lower()}"
                    k = "token"
                    conf = 0.1
                    ent_kind = "token"
                elif kind == "surface":
                    ext = f"surf:{tok}"
                    k = "surface"
                    conf = 0.3
                    ent_kind = "surface"
                else:  # hashtag
                    ext = f"surf:{tok.lower()}"
                    k = "surface"
                    conf = 0.3
                    ent_kind = "surface"
                ent_id = upsert_entity(conn, ext, kind=ent_kind, attrs={k: tok})
                if ent_id < 0:
                    continue
                conn.execute(
                    """
                    INSERT INTO mention (chunk_id, ent_id, span, conf)
                    VALUES (%s, %s, int4range(%s, %s), %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (cid, ent_id, int(s), int(e), conf),
                )
                inserted += 1
    return inserted


def main():
    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
    limit = int(os.environ.get("STUB_LIMIT", "100"))
    with psycopg.connect(dsn) as conn:
        conn.execute("SET TIME ZONE 'UTC'")
        n = process_chunks(conn, limit=limit)
        print(f"[i] entity_link_stub: inserted {n} mentions")


if __name__ == "__main__":
    main()
