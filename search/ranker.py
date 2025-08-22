from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default


def load_source_trust() -> Dict[str, float]:
    raw = os.environ.get("SOURCE_TRUST_JSON", "")
    if not raw:
        return {}
    try:
        m = json.loads(raw)
        if isinstance(m, dict):
            out: Dict[str, float] = {}
            for k, v in m.items():
                try:
                    out[str(k)] = float(v)
                except Exception:
                    continue
            return out
    except Exception:
        pass
    return {}


def recency_decay(published_at: datetime, halflife_h: float) -> float:
    try:
        dt = published_at.astimezone(timezone.utc)
        age_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
        if halflife_h <= 0:
            return 0.0
        return 0.5 ** (age_h / halflife_h)
    except Exception:
        return 0.0


def rerank_candidates(
    rows: Iterable[Tuple[Any, ...]],
    *,
    dist_index: int,
    published_index: int,
    source_index: int,
    limit: int,
) -> List[Tuple[Any, ...]]:
    """
    Apply weighted rank fusion to candidate rows.

    rows: tuples that include distance (cos distance), published_at (datetime), source (str)
    dist_index/published_index/source_index: indices of those fields in row
    limit: number of results to keep
    """
    a = env_float("RANK_ALPHA", 0.7)
    b = env_float("RANK_BETA", 0.2)
    g = env_float("RANK_GAMMA", 0.1)
    ssum = a + b + g
    if ssum <= 0:
        a, b, g = 1.0, 0.0, 0.0
        ssum = 1.0
    a, b, g = a / ssum, b / ssum, g / ssum
    hl = env_float("RECENCY_HALFLIFE_HOURS", 24.0)
    trust_map = load_source_trust()
    trust_default = env_float("SOURCE_TRUST_DEFAULT", 1.0)

    scored: List[Tuple[float, Tuple[Any, ...]]] = []
    for r in rows:
        dist = float(r[dist_index]) if r[dist_index] is not None else 1.0
        cos_sim = 1.0 - max(0.0, min(1.0, dist))
        rec = recency_decay(r[published_index], hl)
        trust = float(trust_map.get(r[source_index], trust_default))
        score = a * cos_sim + b * rec + g * trust
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [sr[1] for sr in scored[:limit]]

