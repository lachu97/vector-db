# vectordb/metrics.py
"""
Prometheus metrics for Vector DB.

Metrics exposed:
  vectordb_requests_total          — Counter  [method, endpoint, status_code]
  vectordb_request_duration_seconds — Histogram [method, endpoint]
  vectordb_vectors_total           — Gauge    [collection]
  vectordb_collections_total       — Gauge    (no labels)

MetricsMiddleware records the first two automatically for every HTTP request.
The gauge metrics are updated explicitly by the application at startup and
after write operations.
"""
import time

import structlog
from fastapi import Request
from fastapi.responses import Response
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Metric definitions (module-level singletons, registered in the default REGISTRY)
# ---------------------------------------------------------------------------

REQUEST_COUNT = Counter(
    "vectordb_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "vectordb_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

VECTORS_TOTAL = Gauge(
    "vectordb_vectors_total",
    "Total number of vectors stored",
    ["collection"],
)

COLLECTIONS_TOTAL = Gauge(
    "vectordb_collections_total",
    "Total number of collections",
)


# ---------------------------------------------------------------------------
# Helper: update collection/vector gauges
# ---------------------------------------------------------------------------

def update_collection_gauges(db_session) -> None:
    """Refresh collection and per-collection vector gauges from the DB."""
    from vectordb.models.db import Collection, Vector

    try:
        collections = db_session.query(Collection).all()
        COLLECTIONS_TOTAL.set(len(collections))
        for col in collections:
            count = db_session.query(Vector).filter_by(collection_id=col.id).count()
            VECTORS_TOTAL.labels(collection=col.name).set(count)
    except Exception as exc:
        logger.warning("metrics_gauge_update_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Records request count and latency for every HTTP request.

    Uses the matched route template (e.g. /v1/collections/{name}/search) as
    the endpoint label to avoid cardinality explosion from dynamic path segments.
    Falls back to the raw URL path when no route is matched.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        # Prefer the route template over the raw path
        route = request.scope.get("route")
        endpoint = route.path if route else request.url.path

        method = request.method
        status = str(response.status_code)

        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

        logger.info(
            "http_request",
            method=method,
            endpoint=endpoint,
            status_code=status,
            duration_ms=round(duration * 1000, 2),
        )

        return response


# ---------------------------------------------------------------------------
# Prometheus scrape response
# ---------------------------------------------------------------------------

def prometheus_response() -> Response:
    """Return the current metrics in Prometheus text exposition format."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
