from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_kv(event: str, **kv: Any) -> None:
    """Emit a one-line JSON log for easier journal scraping.
    Does not raise on serialization errors; falls back to str().
    """
    safe_kv = {}
    for k, v in kv.items():
        try:
            json.dumps(v)
            safe_kv[k] = v
        except Exception:
            safe_kv[k] = str(v)
    line = {"event": str(event), "ts": _iso_utc_now(), "kv": safe_kv}
    try:
        print(json.dumps(line, ensure_ascii=False))
    except Exception:
        # As a last resort, ensure we output something
        print("{" + f"\"event\":\"{event}\",\"ts\":\"{_iso_utc_now()}\"" + "}")

