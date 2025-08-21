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


API_URL = "https://newsapi.org/v2"


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
    """Normalize URL by removing common tracking params and fragment."""
    try:
        u = urlparse.urlsplit(url)
        q = urlparse.parse_qsl(u.query, keep_blank_values=False)
        q = [(k, v) for (k, v) in q if (not k.lower().startswith("utm_")) and (k.lower() not in DROP_KEYS)]
        new_q = urlparse.urlencode(q)
        return urlparse.urlunsplit((u.scheme, u.netloc, u.path, new_q, ""))
    except Exception:
        return url


def to_utc_iso(ts: str | None) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        # NewsAPI: RFC3339 like '2025-08-20T03:12:34Z'
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def insert_article(conn, source_name: str, article: dict, default_genre: str | None):
    title = (article.get("title") or "").strip()
    url = article.get("url") or ""
    if not title or not url:
        return
    url_canon = canonicalize_url(url)
    published_at = to_utc_iso(article.get("publishedAt"))
    lang = article.get("language")  # not always present
    source_uid = article.get("url")  # best-effort unique
    summary = (article.get("description") or "").strip()
    author = article.get("author")

    raw = {
        "source": article.get("source"),
        "author": article.get("author"),
        "title": article.get("title"),
        "description": article.get("description"),
        "url": article.get("url"),
        "publishedAt": article.get("publishedAt"),
        "content": article.get("content"),
    }
    body_for_hash = (summary or title).encode("utf-8", errors="ignore")
    hash_body = psycopg.Binary(hashlib.sha256(body_for_hash).digest())

    doc_id = None
    try:
        with conn.transaction():
            cur = conn.execute(
                """
                INSERT INTO doc (source, source_uid, url_canon, title_raw, author, lang, published_at, hash_body, raw)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url_canon) DO UPDATE SET title_raw = EXCLUDED.title_raw
                RETURNING doc_id
                """,
                (source_name, source_uid, url_canon, title, author, lang, published_at, hash_body, json.dumps(raw)),
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

    if default_genre:
        try:
            conn.execute(
                """
                INSERT INTO hint (doc_id, key, val, conf)
                VALUES (%s, 'genre_hint', %s, %s)
                ON CONFLICT (doc_id, key) DO UPDATE SET val = EXCLUDED.val, conf = EXCLUDED.conf
                """,
                (doc_id, default_genre, 0.6),
            )
        except Exception as ex:
            print(f"[!] hint upsert error: {ex}")


def main():
    ap = argparse.ArgumentParser(description="NewsAPI ingest (v2 minimal)")
    ap.add_argument("--mode", choices=["top", "everything"], default="top")
    ap.add_argument("--country", default="jp")
    ap.add_argument("--category", default=None)
    ap.add_argument("--q", default=None)
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--genre-hint", default=None, help="e.g., medtop:04000000")
    ap.add_argument("--sleep", type=float, default=0.3, help="seconds between requests")
    args = ap.parse_args()

    key = os.environ.get("NEWSAPI_KEY")
    if not key:
        print("[!] Set NEWSAPI_KEY environment variable.")
        sys.exit(2)

    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
    source_name = f"NewsAPI:{args.category or 'general'}:{args.country}"

    with psycopg.connect(dsn) as conn:
        with httpx.Client(timeout=20.0) as client:
            total = 0
            for page in range(1, args.pages + 1):
                params = {"pageSize": args.page_size, "page": page, "apiKey": key}
                if args.mode == "top":
                    url = f"{API_URL}/top-headlines"
                    params.update({"country": args.country})
                    if args.category:
                        params["category"] = args.category
                    if args.q:
                        params["q"] = args.q
                else:
                    url = f"{API_URL}/everything"
                    if args.q:
                        params["q"] = args.q
                    params["sortBy"] = "publishedAt"

                print(f"[+] GET {url} {params}")
                r = client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
                articles = data.get("articles", [])
                for a in articles:
                    insert_article(conn, source_name, a, args.genre_hint)
                    total += 1
                if not articles:
                    break
                time.sleep(args.sleep)

            print(f"[✓] NewsAPI ingest done: {total} items")


if __name__ == "__main__":
    main()
