#!/usr/bin/env python3
"""
Event extraction skeleton.
Extract time, location, and actors from text and map to event tables.

This is a placeholder; actual extraction logic will be implemented later.
"""
from typing import Any, Dict, List, Optional
import re
from .entity_link import extract_entities


def _classify_type(text: str) -> str:
    """Very simple keyword-based type_id classification.
    1000: 会見/発表, 1100: 会談/会合, 1200: 災害, 1300: 裁判/判決, else 9999
    """
    t = text or ""
    if any(k in t for k in ("記者会見", "会見", "発表")):
        return "1000"
    if any(k in t for k in ("会談", "会合", "首脳会談")):
        return "1100"
    if any(k in t for k in ("地震", "台風", "豪雨", "災害", "噴火")):
        return "1200"
    if any(k in t for k in ("裁判", "判決", "起訴", "有罪", "無罪")):
        return "1300"
    return "9999"


_GEOHASH_JP = {
    # coarse, representative geohashes
    "東京": "xn76",
    "東京都": "xn76",
    "大阪": "xn6q",
    "大阪市": "xn6q",
    "名古屋": "xn4k",
    "京都": "xn6h",
    "札幌": "xnh6",
    "福岡": "xn65",
    "那覇": "wgs8",  # Okinawa approx
}


def _detect_loc(text: str) -> Optional[str]:
    for key, gh in _GEOHASH_JP.items():
        if key in (text or ""):
            return gh
    return None


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
            "type_id": _classify_type(text),
            "t_start": ds,
            "t_end": ds,
            "participants": [],
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
            "type_id": _classify_type(text),
            "t_start": ds,
            "t_end": ds,
            "participants": [],
        })
    # Participants (simple reuse of entity extraction)
    parts = extract_entities(text)
    if parts:
        # Wrap as {name, role}
        part_objs = [{"name": p, "role": None} for p in parts]
        for e in out:
            e.setdefault("participants", [])
            e["participants"].extend(part_objs)

    # Simple location mapping (placeholder)
    gh = _detect_loc(text or "")
    if gh:
        for e in out:
            e["loc_geohash"] = gh

    return out


# SQL templates (for reference)
# INSERT INTO event (type_id, t_start, t_end, loc_geohash) VALUES (%s, %s, %s, %s)
# INSERT INTO event_participant (event_id, ent_id, role) VALUES (%s, %s, %s)


if __name__ == "__main__":
    import sys, json
    text = sys.stdin.read()
    events = extract_events(text)
    print(json.dumps({"events": events}, ensure_ascii=False))
