#!/usr/bin/env python3
import argparse
import json
import os
import sys
import hashlib
import urllib.parse as urlparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import psycopg


def canonicalize_url(url: str) -> str:
    """Normalize URL by dropping tracking params and fragment.

    Removes common trackers like utm_*, gclid, fbclid, and clears the fragment.
    """
    try:
        u = urlparse.urlsplit(url)
        q = urlparse.parse_qsl(u.query, keep_blank_values=False)
        blacklist = {"gclid", "fbclid", "yclid", "mc_cid", "mc_eid"}
        q = [
            (k, v)
            for (k, v) in q
            if (not k.lower().startswith("utm_")) and (k.lower() not in blacklist)
        ]
        new_q = urlparse.urlencode(q)
        return urlparse.urlunsplit((u.scheme, u.netloc, u.path, new_q, ""))
    except Exception:
        return url


def to_utc(dt_like) -> datetime:
    if not dt_like:
        return datetime.now(timezone.utc)
    if isinstance(dt_like, datetime):
        if dt_like.tzinfo is None:
            return dt_like.replace(tzinfo=timezone.utc)
        return dt_like.astimezone(timezone.utc)
    # string
    try:
        d = parsedate_to_datetime(str(dt_like))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def load_feeds(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="RSS/Atom ingest (v2 minimal)")
    ap.add_argument("--feeds", required=True, help="feeds.json path")
    ap.add_argument("--source", default="RSS", help="source name")
    ap.add_argument("--genre_hint", default=None, help="hint code (e.g., medtop:04000000)")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
    feeds = load_feeds(args.feeds)

    with psycopg.connect(dsn) as conn:
        conn.execute("SET TIME ZONE 'UTC'")
        for feed in feeds:
            url = feed["url"]
            name = feed.get("name") or args.source
            print(f"[+] Fetch: {name} :: {url}")
            fp = feedparser.parse(url)
            for e in fp.entries:
                title = (e.get("title") or "").strip()
                link = e.get("link") or ""
                url_canon = canonicalize_url(link)
                published = e.get("published") or e.get("updated")
                published_at = to_utc(published)
                summary = (e.get("summary") or e.get("description") or "").strip()
                lang = (e.get("language") or fp.feed.get("language") or None)

                raw = {
                    "feed": {"title": fp.feed.get("title"), "link": fp.feed.get("link")},
                    "entry": {k: e.get(k) for k in ("id","title","link","summary","published","updated","author")}
                }
                body_for_hash = (summary or title).encode("utf-8", errors="ignore")
                hash_body = psycopg.Binary(hashlib.sha256(body_for_hash).digest())

                # Upsert doc
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
                            (name, e.get("id"), url_canon, title, e.get("author"), lang, published_at, hash_body, json.dumps(raw)),
                        )
                        row = cur.fetchone()
                        if row:
                            doc_id = row[0]
                        else:
                            # If conflict and no RETURNING (older PG), fetch id
                            cur2 = conn.execute("SELECT doc_id FROM doc WHERE url_canon=%s", (url_canon,))
                            r2 = cur2.fetchone()
                            doc_id = r2[0] if r2 else None
                except Exception as ex:
                    print(f"[!] doc upsert error: {ex}")
                    continue

                if not doc_id:
                    continue

                # Minimal chunk: 1 per doc using summary/title
                text_raw = summary or title
                if text_raw:
                    try:
                        conn.execute(
                            """
                            INSERT INTO chunk (doc_id, part_ix, text_raw, span, lang)
                            VALUES (%s, %s, %s, NULL, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (doc_id, 0, text_raw, lang),
                        )
                    except Exception as ex:
                        print(f"[!] chunk insert error: {ex}")

                # Optional hint
                code = feed.get("genre_hint") or args.genre_hint
                if code:
                    try:
                        conn.execute(
                            """
                            INSERT INTO hint (doc_id, key, val, conf)
                            VALUES (%s, 'genre_hint', %s, %s)
                            ON CONFLICT (doc_id, key) DO UPDATE SET val = EXCLUDED.val, conf = EXCLUDED.conf
                            """,
                            (doc_id, code, 0.6),
                        )
                    except Exception as ex:
                        print(f"[!] hint upsert error: {ex}")

    print("[✓] ingest done")


if __name__ == "__main__":
    main()
