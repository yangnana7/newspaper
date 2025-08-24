#!/usr/bin/env python3
"""
Link entities to Wikidata QIDs by name.
This script is network-dependent; in CI or offline environments, mock fetch_qid.
"""
import os
import time
from typing import Optional

import psycopg
import requests


WIKIDATA_API = os.environ.get(
    "WIKIDATA_API",
    "https://www.wikidata.org/w/api.php",
)


def fetch_qid(name: str, lang: str = "ja") -> Optional[str]:
    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": lang,
        "format": "json",
        "limit": 1,
    }
    r = requests.get(WIKIDATA_API, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    hits = data.get("search") or []
    if not hits:
        return None
    qid = hits[0].get("id")
    return qid if isinstance(qid, str) and qid.startswith("Q") else None


def _connect():
    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    return psycopg.connect(dsn)


def link_missing(limit: int = 100, sleep_sec: float = 0.3) -> int:
    """Find entities with NULL ext_id, fetch QID, and update when found.
    Returns number of linked entities.
    """
    cnt = 0
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT ent_id, attrs->>'name' AS name
            FROM entity
            WHERE ext_id IS NULL AND attrs ? 'name'
            ORDER BY ent_id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for ent_id, name in rows:
            if not name:
                continue
            try:
                qid = fetch_qid(name)
            except Exception:
                qid = None
            if qid:
                conn.execute(
                    "UPDATE entity SET ext_id=%s WHERE ent_id=%s",
                    (qid, ent_id),
                )
                cnt += 1
            time.sleep(sleep_sec)
    return cnt


if __name__ == "__main__":
    n = link_missing()
    print(f"linked_entities={n}")

