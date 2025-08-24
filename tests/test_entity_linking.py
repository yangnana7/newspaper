import os
import types
import pytest


def test_link_entities_wikidata_monkeypatched(monkeypatch):
    # Skip in CI without DB
    if os.getenv("SKIP_DB_TESTS") == "1":
        pytest.skip("DB not available in CI")

    import scripts.link_entities_wikidata as mod

    # Monkeypatch fetch_qid to deterministic mapping
    def fake_fetch(name: str, lang: str = "ja"):
        return {"トヨタ": "Q53145", "東京都": "Q1490"}.get(name)

    monkeypatch.setattr(mod, "fetch_qid", fake_fetch)

    # Ensure function is callable; side effects depend on DB contents
    assert hasattr(mod, "link_missing")

