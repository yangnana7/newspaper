#!/usr/bin/env python3
"""
Set language codes for doc records.
Uses langdetect when available; falls back to heuristic rules.
"""
import os
from typing import Optional

import psycopg

try:
    from langdetect import detect as _ld_detect  # type: ignore
except Exception:
    _ld_detect = None


def detect_lang(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None
    # Try langdetect
    if _ld_detect is not None:
        try:
            code = _ld_detect(t)
            return code
        except Exception:
            pass
    # Heuristic fallback
    # If contains Hiragana/Katakana, likely Japanese
    if any("\u3040" <= ch <= "\u30ff" for ch in t):
        return "ja"
    # Cyrillic -> Russian
    if any("\u0400" <= ch <= "\u04ff" for ch in t):
        return "ru"
    # CJK Unified Ideographs -> Chinese (undifferentiated)
    if any("\u4e00" <= ch <= "\u9fff" for ch in t):
        return "zh"
    # Basic Latin default -> English
    return "en"


def _connect():
    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    return psycopg.connect(dsn)


def set_missing(limit: int = 1000) -> int:
    """Set language for docs with NULL lang.
    Returns number of updated rows.
    """
    n = 0
    with _connect() as conn:
        rows = conn.execute(
            "SELECT doc_id, COALESCE(title_raw,'') || ' ' || COALESCE(description,'') AS text FROM doc WHERE lang IS NULL ORDER BY doc_id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        for doc_id, text in rows:
            code = detect_lang(text or "")
            if code:
                conn.execute("UPDATE doc SET lang=%s WHERE doc_id=%s", (code, doc_id))
                n += 1
    return n


if __name__ == "__main__":
    try:
        n = set_missing()
        print(f"updated_lang={n}")
    except Exception as e:
        print(f"error: {e}")

