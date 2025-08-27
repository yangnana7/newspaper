import os
import pytest


def test_settings_enforces_fixed_env(monkeypatch):
    from mcp_news.settings import Settings

    # Wrong DB name → exit(2)
    monkeypatch.setenv("DATABASE_URL", "postgresql://127.0.0.1/otherdb")
    monkeypatch.setenv("APP_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("APP_BIND_PORT", "3011")
    s = Settings()
    with pytest.raises(SystemExit):
        s.validate_fixed_env()


def test_settings_ok_typing(monkeypatch):
    from mcp_news.settings import Settings
    monkeypatch.setenv("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    monkeypatch.setenv("APP_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("APP_BIND_PORT", "3011")
    monkeypatch.delenv("EMBED_SPACE", raising=False)
    monkeypatch.setenv("EMBEDDING_SPACE", "e5-multilingual")
    s = Settings()
    s.validate_fixed_env()
    assert s.database_url.endswith("/newshub")
    assert s.app_bind_host == "127.0.0.1"
    assert s.app_bind_port == 3011
    assert isinstance(s.embedding_space, str)

