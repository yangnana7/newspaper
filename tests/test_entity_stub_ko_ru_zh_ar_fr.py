import os
import sys

root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root not in sys.path:
    sys.path.insert(0, root)

from scripts.entity_link_stub import extract_terms


def _kinds(text: str):
    return [k for (_, _, _, k) in extract_terms(text, max_terms=20)]


def test_ko_surface():
    text = "오늘은 한글단어 가 포함되어 있습니다"
    ks = _kinds(text)
    assert any(k == "surface" for k in ks)


def test_ru_surface():
    text = "Это пример КиРиллицы и тест"
    ks = _kinds(text)
    assert any(k == "surface" for k in ks)


def test_zh_surface():
    text = "今天有中文词汇和测试"
    ks = _kinds(text)
    assert any(k == "surface" for k in ks)


def test_ar_surface():
    text = "هذا اختبار باللغة العربية"
    ks = _kinds(text)
    assert any(k == "surface" for k in ks)


def test_fr_uses_en_rule():
    text = "Ceci est un TestToken pour FR"
    ks = _kinds(text)
    # Should catch via EN-like token rule
    assert any(k in ("surface", "token") for k in ks)

