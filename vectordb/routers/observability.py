# vectordb/routers/observability.py
import time

import structlog
from fastapi import APIRouter, Depends

from vectordb.auth import ApiKeyInfo, require_readonly
from vectordb.backends import get_backend
from vectordb.backends.base import VectorBackend
from vectordb.metrics import prometheus_response, update_collection_gauges
from vectordb.services.vector_service import success_response

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["observability"])

_start_time: float = time.monotonic()


def reset_start_time() -> None:
    global _start_time
    _start_time = time.monotonic()


@router.get("/metrics", include_in_schema=False)
def scrape_metrics():
    """Prometheus scrape endpoint — no auth required."""
    return prometheus_response()


@router.get("/v1/health")
async def health(
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    stats = await backend.health_stats()

    # Refresh Prometheus gauges
    from prometheus_client import Gauge
    from vectordb.metrics import COLLECTIONS_TOTAL, VECTORS_TOTAL
    COLLECTIONS_TOTAL.set(stats["total_collections"])
    for col in stats.get("collections", []):
        VECTORS_TOTAL.labels(collection=col["name"]).set(col["vector_count"])

    return success_response({
        "status": "ok",
        "uptime_seconds": round(time.monotonic() - _start_time, 2),
        "total_vectors": stats["total_vectors"],
        "total_collections": stats["total_collections"],
        "collections": stats.get("collections", []),
    })
