#!/usr/bin/env python3
"""
Entity linking skeleton.
Extract person/organization names and (future) link to external IDs.

This is a placeholder; actual NLP/Wikidata integration will be implemented later.
"""
from typing import List
import re

try:
    import spacy  # type: ignore
    _NLP = None
except Exception:
    spacy = None
    _NLP = None


def _fallback_extract(text: str) -> List[str]:
    """Simple heuristics for JA without spaCy.
    - Extract contiguous runs mixing Katakana and Kanji (>=3 chars)
    This captures names such as "テスト組織サンプル" as a single surface form.
    """
    pattern = re.compile(r"([\u30A0-\u30FF\u4E00-\u9FFF]{3,})")
    seen = set()
    out: List[str] = []
    for m in pattern.finditer(text or ""):
        s = m.group(0)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _ensure_nlp():
    global _NLP
    if spacy is None:
        return None
    if _NLP is not None:
        return _NLP
    try:
        _NLP = spacy.load("ja_core_news_sm")
        return _NLP
    except Exception:
        return None


def extract_entities(text: str) -> List[str]:
    """Extract surface forms of named entities from text.
    Uses spaCy model when available; falls back to regex heuristics.
    """
    nlp = _ensure_nlp()
    if nlp is not None:
        try:
            doc = nlp(text or "")
            out = [ent.text for ent in doc.ents if ent.label_ in ("PERSON", "ORG", "GPE", "LOC")]
            # Deduplicate while preserving order
            seen = set()
            uniq = []
            for s in out:
                if s not in seen:
                    seen.add(s)
                    uniq.append(s)
            return uniq if uniq else _fallback_extract(text)
        except Exception:
            pass
    return _fallback_extract(text)


# SQL templates (for reference)
# INSERT INTO entity (ext_id, type_id, name) VALUES (%s, %s, %s)
# INSERT INTO mention (ent_id, chunk_id, span_from, span_to) VALUES (%s, %s, %s, %s)


if __name__ == "__main__":
    import sys, json
    text = sys.stdin.read()
    ents = extract_entities(text)
    print(json.dumps({"entities": ents}, ensure_ascii=False))
