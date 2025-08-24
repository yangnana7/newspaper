def test_extract_events_dates():
    from scripts.event_extract import extract_events

    text = "2025/08/24 に式典。翌日 8月25日 にも関連イベント。"
    events = extract_events(text)
    assert isinstance(events, list)
    assert any(e.get("t_start", "").startswith("2025-08-24") for e in events)
    # Japanese month/day (yearless) will produce 0000-mm-dd
    assert any(e.get("t_start", "").startswith("0000-08-25") for e in events)

