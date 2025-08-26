from datetime import timezone


def test_parse_ts_handles_year_zero_and_utc():
    from scripts.ingest_events import _parse_ts

    # Year 0 (invalid) should become None
    assert _parse_ts("0000-01-30T00:00:00Z") is None

    # Valid ISO with Z becomes aware UTC datetime
    dt = _parse_ts("2025-08-24T00:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(dt)

