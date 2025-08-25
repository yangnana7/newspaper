#!/usr/bin/env python3
"""
Set language codes for doc records.
Uses langdetect when available; falls back to heuristic rules.
"""
import os
import re
from typing import Optional

import psycopg

try:
    from langdetect import detect as _ld_detect  # type: ignore
except Exception:
    _ld_detect = None

# Language aliases and canonicalization rules
_ALIASES = {
    # Chinese variants -> zh
    "zh-cn": "zh",
    "zh-sg": "zh",
    "zh-my": "zh",
    "zh-tw": "zh",
    "zh-hk": "zh",
    "zh-hans": "zh",
    "zh-hant": "zh",
    # Legacy/region variants
    "iw": "he",   # Hebrew old -> he
    "in": "id",   # Indonesian old -> id
    "ji": "yi",
    "pt-br": "pt",
    "pt-pt": "pt",
}


def _canon_lang(code: Optional[str]) -> str:
    """Canonicalize language code: map zh-* -> zh, apply aliases, drop region tags."""
    if not code:
        return "und"
    c = str(code).lower().replace("_", "-")
    if c == "zh" or c.startswith("zh-"):
        return "zh"
    return _ALIASES.get(c, c.split("-")[0])


def detect_lang(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None

    # Script-based hints (robust to detector noise)
    _RE_HAN = re.compile(r"[\u4E00-\u9FFF]")            # CJK unified ideographs
    _RE_KANA = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")  # Hiragana/Katakana
    _RE_HANGUL = re.compile(r"[\u1100-\u11FF\uAC00-\uD7A3]") # Hangul Jamo + Syllables
    _RE_CYR = re.compile(r"[\u0400-\u04FF]")             # Cyrillic

    has_han = bool(_RE_HAN.search(t))
    has_kana = bool(_RE_KANA.search(t))
    has_hangul = bool(_RE_HANGUL.search(t))
    has_cyr = bool(_RE_CYR.search(t))

    # Strong priorities
    if has_kana:
        return "ja"
    if has_hangul and not has_kana:
        return "ko"
    if has_cyr:
        return "ru"

    # Detector + canonicalization
    hint = "zh" if (has_han and not has_kana and not has_hangul) else None
    if _ld_detect is not None:
        try:
            raw = _ld_detect(t)
            canon = _canon_lang(raw)
            if hint == "zh" and canon == "ko":
                return "zh"
            return hint or canon
        except Exception:
            pass

    # Fallback if detector unavailable/failed
    if hint:
        return hint
    # Default to English
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
