"""
Common metrics module for MCP News system.
Avoids duplicate metric registrations between web and MCP server modules.
"""
import asyncio
import functools
from typing import Any, Callable, TypeVar, Union

# Prometheus metrics
try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
    
    # Define metrics (singleton registration)
    items_ingested_total = Counter('items_ingested_total', 'Total number of items ingested')
    embeddings_built_total = Counter('embeddings_built_total', 'Total number of embeddings built')
    ingest_duration_seconds = Histogram('ingest_duration_seconds', 'Time spent ingesting items')
    embed_duration_seconds = Histogram('embed_duration_seconds', 'Time spent building embeddings')
except ImportError:
    PROMETHEUS_AVAILABLE = False
    items_ingested_total = None
    embeddings_built_total = None
    ingest_duration_seconds = None
    embed_duration_seconds = None
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain"


F = TypeVar('F', bound=Callable[..., Any])


def get_metrics_content() -> str:
    """Return Prometheus metrics in text format."""
    if not PROMETHEUS_AVAILABLE or generate_latest is None:
        return "# Prometheus client not available\n"
    
    return generate_latest().decode('utf-8')


def record_ingest_item() -> None:
    """Record that an item was ingested."""
    if PROMETHEUS_AVAILABLE and items_ingested_total is not None:
        items_ingested_total.inc()


def record_embedding_built() -> None:
    """Record that an embedding was built."""
    if PROMETHEUS_AVAILABLE and embeddings_built_total is not None:
        embeddings_built_total.inc()


def time_ingest_operation(func: F) -> F:
    """Decorator to time ingest operations (sync functions)."""
    if not PROMETHEUS_AVAILABLE or ingest_duration_seconds is None:
        return func
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with ingest_duration_seconds.time():
            return func(*args, **kwargs)
    return wrapper


def time_embed_operation(func: F) -> F:
    """Decorator to time embedding operations (sync functions)."""
    if not PROMETHEUS_AVAILABLE or embed_duration_seconds is None:
        return func
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with embed_duration_seconds.time():
            return func(*args, **kwargs)
    return wrapper


def time_ingest_operation_async(func: F) -> F:
    """Decorator to time ingest operations (async functions)."""
    if not PROMETHEUS_AVAILABLE or ingest_duration_seconds is None:
        return func
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = ingest_duration_seconds._timer()
        try:
            result = await func(*args, **kwargs)
            ingest_duration_seconds.observe(ingest_duration_seconds._timer() - start_time)
            return result
        except Exception:
            ingest_duration_seconds.observe(ingest_duration_seconds._timer() - start_time)
            raise
    return wrapper


def time_embed_operation_async(func: F) -> F:
    """Decorator to time embedding operations (async functions).""" 
    if not PROMETHEUS_AVAILABLE or embed_duration_seconds is None:
        return func
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = embed_duration_seconds._timer()
        try:
            result = await func(*args, **kwargs)
            embed_duration_seconds.observe(embed_duration_seconds._timer() - start_time)
            return result
        except Exception:
            embed_duration_seconds.observe(embed_duration_seconds._timer() - start_time)
            raise
    return wrapper