import re
import asyncio
import pytest


def _parse_metric(content: str, name: str) -> float:
    # Match either counter without labels or with labels, in multiline content
    # Example:
    #   items_ingested_total 3
    #   items_ingested_total{label="v"} 3
    pattern = re.compile(
        rf"^{name}(?:\{{[^\}}]*\}})?\s+([0-9eE+\-.]+)$",
        re.MULTILINE,
    )
    m = pattern.search(content)
    return float(m.group(1)) if m else 0.0


def _metrics_available(content: str) -> bool:
    return 'Prometheus client not available' not in content


def test_counters_and_histograms_increment_strict():
    from mcp_news.metrics import (
        get_metrics_content,
        record_ingest_item,
        record_embedding_built,
        time_ingest_operation_async,
        time_embed_operation_async,
    )

    content_before = get_metrics_content()
    if not _metrics_available(content_before):
        pytest.skip('prometheus_client not available')

    # Parse baseline values
    items_before = _parse_metric(content_before, 'items_ingested_total')
    embeds_before = _parse_metric(content_before, 'embeddings_built_total')
    ingest_count_before = _parse_metric(content_before, 'ingest_duration_seconds_count')
    embed_count_before = _parse_metric(content_before, 'embed_duration_seconds_count')

    # Increment counters directly
    record_ingest_item()
    record_embedding_built()

    # Observe histograms via async decorators
    async def run_wrapped():
        @time_ingest_operation_async
        async def _ingest():
            await asyncio.sleep(0)

        @time_embed_operation_async
        async def _embed():
            await asyncio.sleep(0)

        await _ingest()
        await _embed()

    asyncio.run(run_wrapped())

    content_after = get_metrics_content()

    # Validate strict +1 increments
    assert _parse_metric(content_after, 'items_ingested_total') == items_before + 1
    assert _parse_metric(content_after, 'embeddings_built_total') == embeds_before + 1

    # Validate histogram counts increased by at least 1 each (decorators)
    assert _parse_metric(content_after, 'ingest_duration_seconds_count') >= ingest_count_before + 1
    assert _parse_metric(content_after, 'embed_duration_seconds_count') >= embed_count_before + 1
