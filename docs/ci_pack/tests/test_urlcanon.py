from scripts.ingest_rss import canonicalize_url

def test_canonicalize_url_strips_trackers():
    url = "https://example.com/a/b?utm_source=x&utm_medium=y&gclid=123&ok=1#frag"
    out = canonicalize_url(url)
    assert out == "https://example.com/a/b?ok=1"
