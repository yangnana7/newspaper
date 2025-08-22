import os
import json
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

pytest.importorskip("web.app")
from web.app import app


client = TestClient(app)


def test_search_sem_ranking_200():
    # Ensure endpoint responds even without q (fallback)
    r = client.get("/api/search_sem?limit=3")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_search_sem_with_vec_200():
    # Minimal vector (dimension-agnostic in server). Should return 200 with list (maybe empty)
    vec = json.dumps([0.0, 0.0, 0.0])
    # Tweak ranking params to ensure they parse
    os.environ["RANK_ALPHA"] = "0.7"
    os.environ["RANK_BETA"] = "0.2"
    os.environ["RANK_GAMMA"] = "0.1"
    os.environ["RECENCY_HALFLIFE_HOURS"] = "1"
    os.environ["SOURCE_TRUST_JSON"] = json.dumps({"test": 1.0})
    r = client.get("/api/search_sem", params={"limit": 2, "q": vec})
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) <= 2

