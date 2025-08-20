import os
import sys
from typing import List
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib import parse as urlparse

import feedparser
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:///newshub")

# Default RSS feeds (edit as needed)
FEEDS: List[str] = [
    "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "https://rss.asahi.com/rss/asahi/newsheadlines.rdf",
]

DROP_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid"
}

def canonicalize_url(url: str) -> str:
    """Remove trackers and fragments, keep scheme/host/path/clean query."""
    try:
        u = urlparse.urlsplit(url)
        q = urlparse.parse_qsl(u.query, keep_blank_values=False)
        q = [(k, v) for (k, v) in q if k.lower() not in DROP_KEYS]
        new_q = urlparse.urlencode(q)
        return urlparse.urlunsplit((u.scheme, u.netloc, u.path, new_q, ""))
    except Exception:
        return url

def to_utc(dt_like) -> datetime:
    """Convert various date inputs to aware UTC datetime; fallback to now()."""
    if not dt_like:
        return datetime.now(timezone.utc)
    if isinstance(dt_like, datetime):
        if dt_like.tzinfo is None:
            return dt_like.replace(tzinfo=timezone.utc)
        return dt_like.astimezone(timezone.utc)
    try:
        d = parsedate_to_datetime(str(dt_like))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def main(feeds: List[str]) -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        cur = conn.cursor()
        inserted = 0
        for feed_url in feeds:
            d = feedparser.parse(feed_url)
            if getattr(d, "bozo", False):
                print(f"[warn] feed parse error: {feed_url}: {getattr(d, 'bozo_exception', '')}", file=sys.stderr)
            for e in d.entries:
                url = canonicalize_url(getattr(e, "link", ""))
                if not url:
                    continue
                title = getattr(e, "title", "") or "(no title)"
                published = to_utc(getattr(e, "published", getattr(e, "updated", None)))
                lang = getattr(e, "lang", None) or getattr(d.feed, "language", None)

                # Optional summary-based minimal chunk text
                summary = getattr(e, "summary", "") or ""

                # Insert or upsert doc and get doc_id
                row = cur.execute(
                    """
                    INSERT INTO doc (source, url_canon, title_raw, lang, published_at, first_seen_at, raw)
                    VALUES (%s, %s, %s, %s, %s, now(), %s)
                    ON CONFLICT (url_canon) DO UPDATE
                      SET title_raw = EXCLUDED.title_raw,
                          published_at = EXCLUDED.published_at
                    RETURNING doc_id
                    """,
                    (feed_url, url, title, lang, published, {"feed": feed_url})
                ).fetchone()
                doc_id = row[0]

                # Minimal chunk (title + summary)
                text_raw = (title + "\n\n" + summary).strip()
                if text_raw:
                    cur.execute(
                        """
                        INSERT INTO chunk (doc_id, part_ix, text_raw, span, lang, created_at)
                        VALUES (%s, 0, %s, NULL, %s, now())
                        ON CONFLICT DO NOTHING
                        """,
                        (doc_id, text_raw, lang)
                    )
                inserted += 1
        conn.commit()
    print(f"[ok] inserted/updated docs: {inserted}")
    return 0

if __name__ == "__main__":
    feeds_env = os.getenv("RSS_FEEDS")
    feeds = [u.strip() for u in feeds_env.split(",")] if feeds_env else FEEDS
    sys.exit(main(feeds))
