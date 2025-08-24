import importlib


def test_import_order_and_metrics_help():
    # Import in one order
    import mcp_news.server  # noqa: F401
    import web.app  # noqa: F401

    # Re-import modules to ensure no duplicate registration errors
    importlib.reload(importlib.import_module('mcp_news.metrics'))

    # Import in reverse order
    import web.app  # noqa: F401
    import mcp_news.server  # noqa: F401

    # Metrics content should be a text with HELP lines when client is available
    from mcp_news.metrics import get_metrics_content
    content = get_metrics_content()
    assert isinstance(content, str)
    assert ('# HELP' in content) or ('Prometheus client not available' in content)

