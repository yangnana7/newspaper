def test_extract_entities_fallback_and_optional_spacy():
    from scripts.entity_link import extract_entities

    text = "政府関係者がカンファレンスで発表。トヨタ自動車とソニーグループが協力。東京都で会合。"
    ents = extract_entities(text)
    assert isinstance(ents, list)
    # Should extract at least one surface form via fallback regex (e.g., カタカナ語 or 3+ Kanji)
    assert len(ents) >= 1

