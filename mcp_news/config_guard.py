from .settings import Settings


def require_fixed_env() -> None:
    """Enforce fixed environment policy for MCP-First deployment.
    Delegates checks to Settings to centralize environment handling.
    """
    s = Settings()
    s.validate_fixed_env()
