import os
import sys
import pytest

# Ensure repo root is on path when running locally
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root not in sys.path:
    sys.path.insert(0, root)

from scripts.entity_link_stub import extract_terms


def test_extract_terms_japanese_and_hashtag():
    text = "今日はカタカナワードと #HashTag があります ABCtoken"
    terms = extract_terms(text)
    kinds = [k for (_, _, _, k) in terms]
    # Expect at least one surface (katakana) and one hashtag
    assert any(k == "surface" for k in kinds)
    assert any(k == "hashtag" for k in kinds)

