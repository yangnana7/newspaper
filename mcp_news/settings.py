from __future__ import annotations

import os
import sys
from dataclasses import dataclass


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Lightweight settings facade to centralize environment access.
    No external dependencies. Values are read once on instantiation.
    """

    database_url: str = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    app_bind_host: str = os.environ.get("APP_BIND_HOST", "127.0.0.1")
    app_bind_port: int = int(os.environ.get("APP_BIND_PORT", "3011"))

    # Embedding space label (accept legacy var for compatibility)
    embedding_space: str = (
        os.environ.get("EMBED_SPACE")
        or os.environ.get("EMBEDDING_SPACE")
        or "e5-multilingual"
    )
    enable_server_embedding: bool = _get_bool("ENABLE_SERVER_EMBEDDING", False)
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")

    def validate_fixed_env(self) -> None:
        """Enforce fixed environment invariants.
        - DB must be 'newshub'
        - Bind host/port must be 127.0.0.1:3011
        Exit(2) on violation to fail fast per policy.
        """
        if "/newshub" not in self.database_url:
            sys.stderr.write("[FATAL CONFIG] DATABASE_URL must point to database 'newshub'\n")
            raise SystemExit(2)
        if not (self.app_bind_host == "127.0.0.1" and str(self.app_bind_port) == "3011"):
            sys.stderr.write("[FATAL CONFIG] APP_BIND_HOST/PORT must be 127.0.0.1:3011\n")
            raise SystemExit(2)

