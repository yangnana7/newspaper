import asyncio
import pytest


@pytest.mark.asyncio
async def test_async_decorators_record_without_error():
    from mcp_news.metrics import (
        time_ingest_operation_async,
        time_embed_operation_async,
        get_metrics_content,
    )

    @time_ingest_operation_async
    async def dummy_ingest(x: int) -> int:
        await asyncio.sleep(0)
        return x + 1

    @time_embed_operation_async
    async def dummy_embed(x: int) -> int:
        await asyncio.sleep(0)
        return x * 2

    assert await dummy_ingest(1) == 2
    assert await dummy_embed(2) == 4

    # Ensure metrics text contains the histogram names when available
    content = get_metrics_content()
    assert isinstance(content, str)
    # Either histograms appear or the client is not available
    ok = ('ingest_duration_seconds' in content and 'embed_duration_seconds' in content) \
         or ('Prometheus client not available' in content)
    assert ok

