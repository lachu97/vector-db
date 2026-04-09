# vectordb/services/query_service.py
"""Query service: embed query, search, return ranked results."""
import time
from typing import Any, Dict, List, Optional

import structlog

from vectordb.backends.base import VectorBackend
from vectordb.services.embedding_service import embed_text_cached_async

logger = structlog.get_logger(__name__)


async def run_query(
    query: str,
    collection_name: str,
    top_k: int,
    backend: VectorBackend,
    filters: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Embed query, search collection, return (formatted_results, timing_dict)."""
    t0 = time.perf_counter()

    # 1. Async cached embedding (non-blocking, concurrency-limited)
    query_vector = await embed_text_cached_async(query)
    t_embed = time.perf_counter()

    # 2. Search via existing backend
    results = await backend.search(
        collection_name, query_vector, k=top_k, offset=0, filters=filters,
    )
    t_search = time.perf_counter()

    # 3. Format results — extract text from metadata
    formatted = []
    for r in results:
        formatted.append({
            "text": r.get("metadata", {}).get("text", ""),
            "score": r["score"],
            "metadata": r.get("metadata", {}),
            "external_id": r["external_id"],
        })

    timing = {
        "embedding_ms": round((t_embed - t0) * 1000, 2),
        "search_ms": round((t_search - t_embed) * 1000, 2),
        "total_ms": round((t_search - t0) * 1000, 2),
    }

    logger.debug("query_timing", **timing)

    return formatted, timing
