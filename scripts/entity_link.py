#!/usr/bin/env python3
"""
Entity linking skeleton.
Extract person/organization names and (future) link to external IDs.

This is a placeholder; actual NLP/Wikidata integration will be implemented later.
"""
from typing import List


def extract_entities(text: str) -> List[str]:
    """Return a list of surface forms detected in the text.
    Placeholder that returns an empty list.
    """
    # TODO: implement NER (e.g., spaCy) and link to Wikidata
    return []


# SQL templates (for reference)
# INSERT INTO entity (ext_id, type_id, name) VALUES (%s, %s, %s)
# INSERT INTO mention (ent_id, chunk_id, span_from, span_to) VALUES (%s, %s, %s, %s)


if __name__ == "__main__":
    import sys, json
    text = sys.stdin.read()
    ents = extract_entities(text)
    print(json.dumps({"entities": ents}, ensure_ascii=False))

