from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    import yaml
except ImportError:
    yaml = None


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default


def load_ranking_config() -> Dict[str, Any]:
    """Load ranking configuration from YAML file with fallback to defaults."""
    config_path = Path(__file__).parent.parent / "config" / "ranking.yaml"
    
    # Default configuration
    defaults = {
        "score_weights": {
            "cosine": 0.7,
            "recency": 0.2,
            "source_trust": 0.1,
            "language": 0.0,
        },
        "recency_half_life_hours": 48,
        "source_trust": {
            "default": 0.0
        },
        "language_trust": {
            "default": 0.0
        },
    }
    
    if not config_path.exists() or yaml is None:
        return defaults
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        # Merge with defaults
        result = defaults.copy()
        if "score_weights" in config:
            result["score_weights"].update(config["score_weights"])
        if "recency_half_life_hours" in config:
            result["recency_half_life_hours"] = config["recency_half_life_hours"]
        if "source_trust" in config:
            result["source_trust"].update(config["source_trust"])
        if "language_trust" in config:
            result["language_trust"].update(config["language_trust"])
        
        return result
    except Exception:
        return defaults


def load_source_trust() -> Dict[str, float]:
    """Load source trust configuration from YAML config or environment fallback."""
    config = load_ranking_config()
    trust_config = config["source_trust"]
    
    # Convert to float values, excluding 'default' key
    result = {}
    for k, v in trust_config.items():
        if k != "default":
            try:
                result[str(k)] = float(v)
            except Exception:
                continue
    
    # Legacy environment variable fallback
    raw = os.environ.get("SOURCE_TRUST_JSON", "")
    if raw:
        try:
            m = json.loads(raw)
            if isinstance(m, dict):
                for k, v in m.items():
                    try:
                        result[str(k)] = float(v)
                    except Exception:
                        continue
        except Exception:
            pass
    
    return result


def load_language_trust() -> Dict[str, float]:
    """Load language trust configuration from YAML config."""
    config = load_ranking_config()
    trust_config = config.get("language_trust", {})
    result: Dict[str, float] = {}
    for k, v in trust_config.items():
        if k != "default":
            try:
                result[str(k)] = float(v)
            except Exception:
                continue
    return result


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
    language_index: int | None = None,
    limit: int,
) -> List[Tuple[Any, ...]]:
    """
    Apply weighted rank fusion to candidate rows.

    rows: tuples that include distance (cos distance), published_at (datetime), source (str)
    dist_index/published_index/source_index: indices of those fields in row
    limit: number of results to keep
    """
    # Load configuration from YAML with environment variable fallbacks
    config = load_ranking_config()
    weights = config["score_weights"]
    
    # Environment variables take precedence for backward compatibility
    a = env_float("RANK_ALPHA", weights.get("cosine", 0.7))
    b = env_float("RANK_BETA", weights.get("recency", 0.2))
    g = env_float("RANK_GAMMA", weights.get("source_trust", 0.1))
    dlt = env_float("RANK_DELTA", weights.get("language", 0.0))
    
    ssum = a + b + g + dlt
    if ssum <= 0:
        a, b, g, dlt = 1.0, 0.0, 0.0, 0.0
        ssum = 1.0
    a, b, g, dlt = a / ssum, b / ssum, g / ssum, dlt / ssum
    
    hl = env_float("RECENCY_HALFLIFE_HOURS", config["recency_half_life_hours"])
    trust_map = load_source_trust()
    lang_map = load_language_trust()
    trust_default = env_float("SOURCE_TRUST_DEFAULT", config["source_trust"]["default"])
    lang_default = env_float("LANGUAGE_TRUST_DEFAULT", config["language_trust"].get("default", 0.0))

    scored: List[Tuple[float, Tuple[Any, ...]]] = []
    for r in rows:
        dist = float(r[dist_index]) if r[dist_index] is not None else 1.0
        cos_sim = 1.0 - max(0.0, min(1.0, dist))
        rec = recency_decay(r[published_index], hl)
        trust = float(trust_map.get(r[source_index], trust_default))
        lang_val = 0.0
        if language_index is not None:
            lang_code = r[language_index]
            if lang_code is not None:
                try:
                    lang_val = float(lang_map.get(str(lang_code), lang_default))
                except Exception:
                    lang_val = lang_default
            else:
                lang_val = lang_default
        score = a * cos_sim + b * rec + g * trust + dlt * lang_val
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [sr[1] for sr in scored[:limit]]
