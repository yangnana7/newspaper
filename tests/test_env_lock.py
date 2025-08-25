import os


def test_database_url_locked():
    url = os.environ.get("DATABASE_URL", "")
    assert "/newshub" in url, "DB must be 'newshub'"


def test_bind_locked():
    assert os.environ.get("APP_BIND_HOST") == "127.0.0.1"
    assert os.environ.get("APP_BIND_PORT") == "3011"

