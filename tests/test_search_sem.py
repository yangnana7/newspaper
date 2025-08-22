import os
import json
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

pytest.importorskip("web.app")
from web.app import app


def _ensure_test_db_env():
    # Align with other tests' default when DATABASE_URL is unset.
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/testdb",
    )


client = TestClient(app)


def test_sem_no_vec_fallback_ok():
    _ensure_test_db_env()
    r = client.get("/api/search_sem?limit=3")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_sem_with_vec_len_bound():
    _ensure_test_db_env()
    # Minimal zero-vector of dimension 768; server will accept any float array.
    vec = json.dumps([0.0] * 3)  # dimension not enforced here; DB may return empty
    r = client.get("/api/search_sem", params={"limit": 2, "q": vec})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 2


def test_ilike_endpoint_ok():
    _ensure_test_db_env()
    r = client.get("/api/search", params={"q": "a", "limit": 1, "offset": 0})
    assert r.status_code == 200
    assert isinstance(r.json(), list)

