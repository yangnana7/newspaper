#!/usr/bin/env python3
"""
Link entities to Wikidata QIDs by name.
This script is network-dependent; in CI or offline environments, mock fetch_qid.
"""
import os
import time
from typing import Optional, Tuple, Dict, Any, Set

import psycopg
import requests
try:
    import yaml  # type: ignore
except Exception:
    yaml = None


WIKIDATA_API = os.environ.get("WIKIDATA_API", "https://www.wikidata.org/w/api.php")


def _load_linking_config() -> Dict[str, Any]:
    cfg = {
        "min_confidence": 0.6,
        "requests_per_sec": 2.0,
        "max_retries": 2,
        "blacklist_keywords": ["曖昧さ回避", "disambiguation"],
        "prefer_lang": os.environ.get("WIKIDATA_LANG", "ja"),
        "progress_file": os.environ.get("LINK_PROGRESS_FILE", "tmp/linking_progress.txt"),
    }
    if yaml is None:
        return cfg
    path = os.path.join(os.path.dirname(__file__), "..", "config", "linking.yaml")
    path = os.path.normpath(path)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                y = yaml.safe_load(f) or {}
            for k, v in y.items():
                cfg[k] = v
    except Exception:
        pass
    return cfg


def _score_candidate(name: str, item: Dict[str, Any], blacklist: Set[str]) -> float:
    """Compute a naive confidence score for a Wikidata search candidate.
    Presence of blacklist keywords in description reduces confidence.
    Exact match types boost confidence.
    """
    conf = 0.5
    match = item.get("match") or {}
    mtype = match.get("type")
    if mtype == "exact":
        conf = 0.9
    elif mtype:
        conf = 0.65
    label = item.get("label") or ""
    desc = item.get("description") or ""
    text = f"{label} {desc}"
    if any(b in text for b in blacklist):
        conf -= 0.3
    # mild bonus for label equality
    if label and label == name:
        conf += 0.05
    return max(0.0, min(1.0, conf))


def fetch_qid(name: str, lang: str = "ja") -> Optional[str]:
    # Backward-compatible wrapper
    qid, _ = fetch_qid_with_confidence(name, lang)
    return qid


def fetch_qid_with_confidence(name: str, lang: str = "ja") -> Tuple[Optional[str], float]:
    """Search Wikidata and return (qid, confidence)."""
    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": lang,
        "format": "json",
        "limit": 1,
    }
    r = requests.get(WIKIDATA_API, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    hits = data.get("search") or []
    if not hits:
        return None, 0.0
    top = hits[0]
    qid = top.get("id")
    # load config to use blacklist words
    cfg = _load_linking_config()
    bl = set(map(str, cfg.get("blacklist_keywords", [])))
    conf = _score_candidate(name, top, bl)
    if not (isinstance(qid, str) and qid.startswith("Q")):
        return None, conf
    return qid, conf


def _connect():
    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    return psycopg.connect(dsn)


def _load_progress_set(path: str) -> Set[int]:
    done: Set[int] = set()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        done.add(int(line))
                    except Exception:
                        continue
    except Exception:
        pass
    return done


def _append_progress(path: str, ent_id: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{ent_id}\n")


def link_missing(limit: int = 100, sleep_sec: float = 0.3) -> int:
    """Find entities with NULL ext_id, fetch QID, and update when found.
    Applies naive confidence filtering and basic rate limiting. Writes progress to a file to allow resume.
    Returns number of linked entities.
    """
    cfg = _load_linking_config()
    min_conf = float(cfg.get("min_confidence", 0.6))
    rps = float(cfg.get("requests_per_sec", 2.0))
    backoff_max = int(cfg.get("max_retries", 2))
    progress_file = str(cfg.get("progress_file", "tmp/linking_progress.txt"))
    # derive sleep from rps (take the maximum pause)
    sleep_between = max(sleep_sec, 1.0 / rps if rps > 0 else sleep_sec)

    processed = _load_progress_set(progress_file)
    cnt = 0
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT ent_id, attrs->>'name' AS name
            FROM entity
            WHERE ext_id IS NULL AND attrs ? 'name'
            ORDER BY ent_id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for ent_id, name in rows:
            if not name or ent_id in processed:
                _append_progress(progress_file, ent_id)
                continue
            qid: Optional[str] = None
            conf: float = 0.0
            # retry loop
            for attempt in range(backoff_max + 1):
                try:
                    qid, conf = fetch_qid_with_confidence(name, cfg.get("prefer_lang", "ja"))
                    break
                except Exception:
                    if attempt >= backoff_max:
                        qid = None
                        conf = 0.0
                        break
                    time.sleep(0.5 * (attempt + 1))
            # confidence gate
            if qid and conf >= min_conf:
                conn.execute("UPDATE entity SET ext_id=%s WHERE ent_id=%s", (qid, ent_id))
                try:
                    from mcp_news.metrics import record_entity_linked  # local import
                    record_entity_linked()
                except Exception:
                    pass
                cnt += 1
            # progress + rate-limit pause
            _append_progress(progress_file, ent_id)
            time.sleep(sleep_between)
    return cnt


if __name__ == "__main__":
    n = link_missing()
    print(f"linked_entities={n}")
