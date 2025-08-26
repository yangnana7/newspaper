#!/usr/bin/env python3
"""
Ingest events extracted from chunk text using scripts/event_extract.py.
DB access occurs only when this script is executed.
"""
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import psycopg

from .event_extract import extract_events
from .entity_link import extract_entities


def _parse_ts(value: Any) -> Optional[datetime]:
    """Best-effort parse to UTC timestamptz acceptable by Postgres.
    Returns None on invalid/unsupported values.
    - Accepts datetime or ISO-like strings. Handles trailing 'Z'.
    - Filters out year 0 and other out-of-range values to avoid PG errors.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            s = str(value).strip()
            if not s:
                return None
            # Normalize trailing 'Z' to +00:00 for fromisoformat
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            # Try parse; fallback to simple YYYY-MM-DD case
            try:
                dt = datetime.fromisoformat(s)
            except Exception:
                # Minimal fallback: take date part only
                try:
                    dt = datetime.fromisoformat(s.split("T")[0])
                except Exception:
                    return None
        except Exception:
            return None
    # Ensure tz-aware UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    # Postgres has no year 0; guard against pathological dates
    if dt.year <= 0:
        return None
    return dt


def _connect():
    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    return psycopg.connect(dsn)


def ingest(limit: int = 1000) -> int:
    count = 0
    with _connect() as conn:
        rows = conn.execute(
            "SELECT c.chunk_id, c.text_raw FROM chunk c ORDER BY c.chunk_id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        for cid, text in rows:
            events: List[Dict[str, Any]] = extract_events(text or "")
            for ev in events:
                t_start = _parse_ts(ev.get("t_start"))
                t_end = _parse_ts(ev.get("t_end"))
                r = conn.execute(
                    "INSERT INTO event (type_id, t_start, t_end, loc_geohash, attrs) VALUES (%s, %s, %s, %s, NULL) RETURNING event_id",
                    (str(ev.get("type_id")), t_start, t_end, ev.get("loc_geohash")),
                ).fetchone()
                event_id = r[0]
                conn.execute(
                    "INSERT INTO evidence (event_id, doc_id, chunk_id, weight) SELECT %s, d.doc_id, %s, 1.0 FROM chunk c JOIN doc d USING(doc_id) WHERE c.chunk_id=%s",
                    (event_id, cid, cid),
                )
                # participants
                has_participant = False
                for part in (ev.get("participants") or []):
                    # accept both legacy string and new dict form
                    if isinstance(part, dict):
                        name = part.get("name")
                        role = part.get("role") or "participant"
                    else:
                        name = part
                        role = "participant"
                    if not name:
                        continue
                    er = conn.execute(
                        "SELECT ent_id FROM entity WHERE attrs->>'name'=%s",
                        (name,),
                    ).fetchone()
                    if er:
                        ent_id = er[0]
                    else:
                        er = conn.execute(
                            "INSERT INTO entity (ext_id, kind, attrs) VALUES (NULL, NULL, jsonb_build_object('name', %s::text)) RETURNING ent_id",
                            (name,),
                        ).fetchone()
                        ent_id = er[0]
                    conn.execute(
                        "INSERT INTO event_participant (event_id, role, ent_id) VALUES (%s, COALESCE(%s,'participant'), %s) ON CONFLICT DO NOTHING",
                        (event_id, role, ent_id),
                    )
                    has_participant = True
                if has_participant:
                    try:
                        from mcp_news.metrics import record_event_with_participants
                        record_event_with_participants()
                    except Exception:
                        pass
                count += 1
    return count


if __name__ == "__main__":
    n = ingest()
    print(f"ingested_events={n}")
