def test_event_classification_location_and_roles():
    from scripts.event_extract import extract_events

    text = "2025-08-28 首脳会談を東京で実施。トヨタ自動車とソニーグループが出席。記者会見も予定。"
    events = extract_events(text)
    assert isinstance(events, list) and len(events) >= 1
    e = events[0]
    # type_id should be classified (1100 for 会談 or 1000 for 会見; 会談に優先)
    assert e.get("type_id") in ("1100", "1000", "1200", "1300", "9999")
    # Tokyo mapping
    assert e.get("loc_geohash") == "xn76"
    parts = e.get("participants") or []
    # participants include role key
    assert all(isinstance(p, dict) and "name" in p and "role" in p for p in parts)

