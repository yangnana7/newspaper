def test_import_order_and_metrics_help():
    # Import in an order (should not raise)
    import mcp_news.server  # noqa: F401
    import web.app  # noqa: F401

    # Metrics content should be a text with HELP lines when client is available
    from mcp_news.metrics import get_metrics_content
    content = get_metrics_content()
    assert isinstance(content, str)
    assert ('# HELP' in content) or ('Prometheus client not available' in content)
