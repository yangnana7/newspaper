"""
Common metrics module for MCP News system.
Avoids duplicate metric registrations between web and MCP server modules.
"""
import asyncio
import functools
import time
from typing import Any, Callable, TypeVar, Union

# Prometheus metrics
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
    
    # Define metrics (singleton registration)
    items_ingested_total = Counter('items_ingested_total', 'Total number of items ingested')
    embeddings_built_total = Counter('embeddings_built_total', 'Total number of embeddings built')
    # New metrics for entity linking and events
    entities_linked_total = Counter('entities_linked_total', 'Total number of entities linked to external IDs')
    events_with_participants_total = Counter('events_with_participants_total', 'Total events recorded with participants')
    ingest_duration_seconds = Histogram('ingest_duration_seconds', 'Time spent ingesting items')
    embed_duration_seconds = Histogram('embed_duration_seconds', 'Time spent building embeddings')
    # Additional metrics (v3)
    search_requests_total = Counter('search_requests_total', 'Total number of search requests processed')
    embed_latency_seconds = Histogram('embed_latency_seconds', 'Latency of embedding operations')
    dup_ratio = Gauge('dup_ratio', 'Near-duplicate ratio of ingested documents')
except ImportError:
    PROMETHEUS_AVAILABLE = False
    items_ingested_total = None
    embeddings_built_total = None
    ingest_duration_seconds = None
    embed_duration_seconds = None
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain"
    entities_linked_total = None
    events_with_participants_total = None
    search_requests_total = None
    embed_latency_seconds = None
    dup_ratio = None


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


def record_entity_linked() -> None:
    """Record that an entity was linked to an external ID."""
    if PROMETHEUS_AVAILABLE and entities_linked_total is not None:
        entities_linked_total.inc()


def record_event_with_participants() -> None:
    """Record that an event with participants was stored."""
    if PROMETHEUS_AVAILABLE and events_with_participants_total is not None:
        events_with_participants_total.inc()


def record_search_request() -> None:
    """Record that a search request occurred."""
    if PROMETHEUS_AVAILABLE and search_requests_total is not None:
        search_requests_total.inc()


def set_dup_ratio(value: float) -> None:
    """Set near-duplicate ratio gauge."""
    if PROMETHEUS_AVAILABLE and dup_ratio is not None:
        try:
            dup_ratio.set(float(value))
        except Exception:
            pass


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
        t0 = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            ingest_duration_seconds.observe(time.perf_counter() - t0)
    return wrapper


def time_embed_operation_async(func: F) -> F:
    """Decorator to time embedding operations (async functions).""" 
    if not PROMETHEUS_AVAILABLE or embed_duration_seconds is None:
        return func
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            embed_duration_seconds.observe(time.perf_counter() - t0)
    return wrapper
