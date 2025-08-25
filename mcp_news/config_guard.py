import os
import sys


def _die(msg: str) -> None:
    sys.stderr.write(f"[FATAL CONFIG] {msg}\n")
    sys.exit(2)


def require_fixed_env() -> None:
    """Enforce fixed environment policy for MCP-First deployment.
    - DATABASE_URL must point to the 'newshub' database
    - APP_BIND_HOST/PORT must be 127.0.0.1:3011
    - Embedding space env must be set (EMBEDDING_SPACE or EMBED_SPACE)
    """
    url = os.environ.get("DATABASE_URL", "")
    if "/newshub" not in url:
        _die("DATABASE_URL must point to database 'newshub'")

    host = os.environ.get("APP_BIND_HOST", "")
    port = os.environ.get("APP_BIND_PORT", "")
    if host != "127.0.0.1" or str(port) != "3011":
        _die("APP_BIND_HOST/PORT must be 127.0.0.1:3011")

    # accept both names for backward compatibility
    space = os.environ.get("EMBEDDING_SPACE") or os.environ.get("EMBED_SPACE")
    if not space:
        _die("EMBEDDING_SPACE/EMBED_SPACE must be set (e.g., e5-multilingual)")

