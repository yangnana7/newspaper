#!/usr/bin/env python3
"""
Event extraction skeleton.
Extract time, location, and actors from text and map to event tables.

This is a placeholder; actual extraction logic will be implemented later.
"""
from typing import Any, Dict, List
import re


def extract_events(text: str) -> List[Dict[str, Any]]:
    """Extract simple date-only events from text.
    Returns a list of dicts with keys: type_id, t_start, t_end, participants.
    t_start/t_end are ISO-like strings when parseable, else None.
    """
    if not text:
        return []
    out: List[Dict[str, Any]] = []
    # Find dates like 2025/08/24 or 2025-08-24
    for m in re.finditer(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text):
        y, mo, d = m.groups()
        ds = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}T00:00:00Z"
        out.append({
            "type_id": 9999,
            "t_start": ds,
            "t_end": ds,
            "participants": []
        })
    # Japanese style like ８月２４日 or 8月24日 (no year)
    for m in re.finditer(r"([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日", text):
        mo, d = m.groups()
        # Normalize zenkaku digits
        trans = str.maketrans("０１２３４５６７８９", "0123456789")
        mo_i = int(str(mo).translate(trans))
        d_i = int(str(d).translate(trans))
        ds = f"0000-{mo_i:02d}-{d_i:02d}T00:00:00Z"
        out.append({
            "type_id": 9999,
            "t_start": ds,
            "t_end": ds,
            "participants": []
        })
    return out


# SQL templates (for reference)
# INSERT INTO event (type_id, t_start, t_end, loc_geohash) VALUES (%s, %s, %s, %s)
# INSERT INTO event_participant (event_id, ent_id, role) VALUES (%s, %s, %s)


if __name__ == "__main__":
    import sys, json
    text = sys.stdin.read()
    events = extract_events(text)
    print(json.dumps({"events": events}, ensure_ascii=False))
