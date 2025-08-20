#!/usr/bin/env python3
import argparse
import os
import sys
import json
import time
import hashlib
from datetime import datetime, timezone
import urllib.parse as urlparse

import httpx
import psycopg


BASE = "https://hacker-news.firebaseio.com/v0"


DROP_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}


def canonicalize_url(url: str) -> str:
    try:
        u = urlparse.urlsplit(url)
        q = urlparse.parse_qsl(u.query, keep_blank_values=False)
        q = [(k, v) for (k, v) in q if (not k.lower().startswith("utm_")) and (k.lower() not in DROP_KEYS)]
        new_q = urlparse.urlencode(q)
        return urlparse.urlunsplit((u.scheme, u.netloc, u.path, new_q, ""))
    except Exception:
        return url


def to_utc(ts: int | None) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def insert_story(conn, item: dict):
    if item.get("type") != "story":
        return
    title = (item.get("title") or "").strip()
    url = item.get("url") or ""
    if not title or not url:
        return
    url_canon = canonicalize_url(url)
    published_at = to_utc(item.get("time"))
    source_uid = str(item.get("id"))
    lang = None
    summary = (item.get("text") or "").strip()

    raw = {
        k: item.get(k)
        for k in ("id", "by", "score", "title", "url", "time", "descendants")
    }
    body_for_hash = (summary or title).encode("utf-8", errors="ignore")
    hash_body = psycopg.Binary(hashlib.sha256(body_for_hash).digest())

    doc_id = None
    try:
        with conn.transaction():
            cur = conn.execute(
                """
                INSERT INTO doc (source, source_uid, url_canon, title_raw, lang, published_at, hash_body, raw)
                VALUES ('HackerNews', %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url_canon) DO UPDATE SET title_raw = EXCLUDED.title_raw
                RETURNING doc_id
                """,
                (source_uid, url_canon, title, lang, published_at, hash_body, json.dumps(raw)),
            )
            r = cur.fetchone()
            if r:
                doc_id = r[0]
            else:
                r2 = conn.execute("SELECT doc_id FROM doc WHERE url_canon=%s", (url_canon,)).fetchone()
                doc_id = r2[0] if r2 else None
    except Exception as ex:
        print(f"[!] doc upsert error: {ex}")
        return

    if not doc_id:
        return

    text_raw = summary or title
    if text_raw:
        try:
            conn.execute(
                """
                INSERT INTO chunk (doc_id, part_ix, text_raw, span, lang)
                VALUES (%s, 0, %s, NULL, %s)
                ON CONFLICT DO NOTHING
                """,
                (doc_id, text_raw, lang),
            )
        except Exception as ex:
            print(f"[!] chunk insert error: {ex}")


def main():
    ap = argparse.ArgumentParser(description="Hacker News ingest (v2 minimal)")
    ap.add_argument("--kind", choices=["topstories", "newstories", "beststories"], default="topstories")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--sleep", type=float, default=0.1)
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
    with psycopg.connect(dsn) as conn:
        with httpx.Client(timeout=20.0) as client:
            url = f"{BASE}/{args.kind}.json"
            print(f"[+] GET {url}")
            ids = client.get(url).json()[: args.limit]
            total = 0
            for i in ids:
                iu = f"{BASE}/item/{i}.json"
                try:
                    it = client.get(iu)
                    it.raise_for_status()
                    item = it.json()
                except Exception as ex:
                    print(f"[!] fetch item {i} error: {ex}")
                    continue
                insert_story(conn, item)
                total += 1
                time.sleep(args.sleep)
            print(f"[✓] HN ingest done: {total} items")


if __name__ == "__main__":
    main()
