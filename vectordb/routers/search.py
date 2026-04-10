# vectordb/routers/search.py
import time

import structlog
from fastapi import APIRouter, Depends

from vectordb.auth import ApiKeyInfo, require_readonly
from vectordb.backends import get_backend
from vectordb.backends.base import (
    CollectionNotFoundError,
    DimensionMismatchError,
    VectorNotFoundError,
    VectorBackend,
)
from vectordb.models.schemas import BulkSearchRequest, HybridSearchRequest, RerankRequest, SearchRequest
from vectordb.services.embedding_service import embed_text_cached_async
from vectordb.services.vector_service import error_response, success_response

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["search"])

DEFAULT_COLLECTION = "default"


async def _ensure_default(backend: VectorBackend):
    from vectordb.backends.base import CollectionAlreadyExistsError
    from vectordb.config import get_settings
    if hasattr(backend, "ensure_default_collection"):
        return await backend.ensure_default_collection()
    col = await backend.get_collection(DEFAULT_COLLECTION)
    if col:
        return col
    try:
        return await backend.create_collection(DEFAULT_COLLECTION, get_settings().vector_dim, "cosine")
    except CollectionAlreadyExistsError:
        return await backend.get_collection(DEFAULT_COLLECTION)


# ------------------------------------------------------------------
# Collection-scoped endpoints
# ------------------------------------------------------------------

async def _check_collection_access(backend, collection_name, user_id):
    """Verify the user has access to this collection. Returns error response or None."""
    col = await backend.get_collection(collection_name, user_id=user_id)
    if not col:
        return error_response(404, f"Collection '{collection_name}' not found")
    return None


@router.post("/collections/{collection_name}/search")
async def search_in_collection(
    collection_name: str,
    req: SearchRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    t_start = time.perf_counter()
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err

    # Resolve text → vector via embedding_service (async, cached)
    vector = req.vector
    embedding_ms = 0.0
    if not vector and req.text:
        t0 = time.perf_counter()
        vector = await embed_text_cached_async(req.text)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)

    try:
        t_search = time.perf_counter()
        results = await backend.search(collection_name, vector, req.k, req.offset, req.filters)
        total_count = await backend.count_vectors(collection_name, req.filters)
        search_ms = round((time.perf_counter() - t_search) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "search_ms": search_ms, "total_ms": total_ms}
        logger.debug("search_timing", **timing, endpoint="search")

        data = {"results": results, "total_count": total_count, "k": req.k, "offset": req.offset}
        if req.include_timing:
            data["timing_ms"] = timing
        return success_response(data)
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except DimensionMismatchError as e:
        return error_response(400, str(e))


@router.post("/collections/{collection_name}/recommend/{external_id}")
async def recommend_in_collection(
    collection_name: str,
    external_id: str,
    k: int = 5,
    ef: int = 50,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err
    try:
        results = await backend.recommend(collection_name, external_id, k, ef)
        return success_response({"results": results})
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except VectorNotFoundError as e:
        return error_response(404, str(e))


@router.post("/collections/{collection_name}/similarity")
async def similarity_in_collection(
    collection_name: str,
    id1: str,
    id2: str,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err
    try:
        score = await backend.similarity(collection_name, id1, id2)
        return success_response({"score": score})
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except VectorNotFoundError:
        return error_response(404, "One or both IDs not found")


@router.post("/collections/{collection_name}/rerank")
async def rerank_in_collection(
    collection_name: str,
    req: RerankRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    t_start = time.perf_counter()
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err

    # Resolve text → vector via embedding_service (async, cached)
    vector = req.vector
    embedding_ms = 0.0
    if not vector and req.text:
        t0 = time.perf_counter()
        vector = await embed_text_cached_async(req.text)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)

    try:
        t_search = time.perf_counter()
        results = await backend.rerank(collection_name, vector, req.candidates)
        search_ms = round((time.perf_counter() - t_search) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "search_ms": search_ms, "total_ms": total_ms}
        logger.debug("rerank_timing", **timing, endpoint="rerank")

        data = {"results": results}
        if req.include_timing:
            data["timing_ms"] = timing
        return success_response(data)
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except DimensionMismatchError as e:
        return error_response(400, str(e))


@router.post("/collections/{collection_name}/hybrid_search")
async def hybrid_search_in_collection(
    collection_name: str,
    req: HybridSearchRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    t_start = time.perf_counter()
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err
    if not (0.0 <= req.alpha <= 1.0):
        return error_response(400, "alpha must be between 0.0 and 1.0")

    # Auto-embed query_text if vector not provided
    vector = req.vector
    embedding_ms = 0.0
    if not vector:
        t0 = time.perf_counter()
        vector = await embed_text_cached_async(req.query_text)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)

    try:
        t_search = time.perf_counter()
        results = await backend.hybrid_search(
            collection_name, req.query_text, vector, req.k, req.offset, req.alpha, req.filters
        )
        search_ms = round((time.perf_counter() - t_search) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "search_ms": search_ms, "total_ms": total_ms}
        logger.debug("hybrid_search_timing", **timing, endpoint="hybrid_search")

        data = {"results": results}
        if req.include_timing:
            data["timing_ms"] = timing
        return success_response(data)
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except DimensionMismatchError as e:
        return error_response(400, str(e))


@router.post("/collections/{collection_name}/bulk_search")
async def bulk_search_in_collection(
    collection_name: str,
    req: BulkSearchRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err

    # Validate vector dimensions match collection
    col = await backend.get_collection(collection_name, user_id=auth.user_id)
    for i, q in enumerate(req.queries):
        if len(q.vector) != col["dim"]:
            return error_response(
                400, f"Query {i}: vector dimension {len(q.vector)} does not match collection dimension {col['dim']}"
            )

    try:
        queries = [{"vector": q.vector, "k": q.k, "filters": q.filters} for q in req.queries]
        results = await backend.bulk_search(collection_name, queries, user_id=auth.user_id)
        return success_response({"results": results})
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except DimensionMismatchError as e:
        return error_response(400, str(e))


# ------------------------------------------------------------------
# Legacy endpoints (route to "default" collection)
# ------------------------------------------------------------------

@router.post("/search")
async def search_legacy(
    req: SearchRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    t_start = time.perf_counter()
    await _ensure_default(backend)

    vector = req.vector
    embedding_ms = 0.0
    if not vector and req.text:
        t0 = time.perf_counter()
        vector = await embed_text_cached_async(req.text)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)

    try:
        t_search = time.perf_counter()
        results = await backend.search(DEFAULT_COLLECTION, vector, req.k, req.offset, req.filters)
        total_count = await backend.count_vectors(DEFAULT_COLLECTION, req.filters)
        search_ms = round((time.perf_counter() - t_search) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "search_ms": search_ms, "total_ms": total_ms}
        logger.debug("search_timing", **timing, endpoint="search_legacy")

        data = {"results": results, "total_count": total_count, "k": req.k, "offset": req.offset}
        if req.include_timing:
            data["timing_ms"] = timing
        return success_response(data)
    except (CollectionNotFoundError, DimensionMismatchError) as e:
        return error_response(400, str(e))


@router.post("/recommend/{external_id}")
async def recommend_legacy(
    external_id: str,
    k: int = 5,
    ef: int = 50,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    await _ensure_default(backend)
    try:
        results = await backend.recommend(DEFAULT_COLLECTION, external_id, k, ef)
        return success_response({"results": results})
    except VectorNotFoundError as e:
        return error_response(404, str(e))
    except CollectionNotFoundError as e:
        return error_response(404, str(e))


@router.post("/similarity")
async def similarity_legacy(
    id1: str,
    id2: str,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    await _ensure_default(backend)
    try:
        score = await backend.similarity(DEFAULT_COLLECTION, id1, id2)
        return success_response({"score": score})
    except VectorNotFoundError:
        return error_response(404, "One or both IDs not found")


@router.post("/rerank")
async def rerank_legacy(
    req: RerankRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    t_start = time.perf_counter()
    await _ensure_default(backend)

    vector = req.vector
    embedding_ms = 0.0
    if not vector and req.text:
        t0 = time.perf_counter()
        vector = await embed_text_cached_async(req.text)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)

    try:
        t_search = time.perf_counter()
        results = await backend.rerank(DEFAULT_COLLECTION, vector, req.candidates)
        search_ms = round((time.perf_counter() - t_search) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "search_ms": search_ms, "total_ms": total_ms}
        logger.debug("rerank_timing", **timing, endpoint="rerank_legacy")

        data = {"results": results}
        if req.include_timing:
            data["timing_ms"] = timing
        return success_response(data)
    except (CollectionNotFoundError, DimensionMismatchError) as e:
        return error_response(400, str(e))


@router.post("/hybrid_search")
async def hybrid_search_legacy(
    req: HybridSearchRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    t_start = time.perf_counter()
    if not (0.0 <= req.alpha <= 1.0):
        return error_response(400, "alpha must be between 0.0 and 1.0")
    await _ensure_default(backend)

    vector = req.vector
    embedding_ms = 0.0
    if not vector:
        t0 = time.perf_counter()
        vector = await embed_text_cached_async(req.query_text)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)

    try:
        t_search = time.perf_counter()
        results = await backend.hybrid_search(
            DEFAULT_COLLECTION, req.query_text, vector, req.k, req.offset, req.alpha, req.filters
        )
        search_ms = round((time.perf_counter() - t_search) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "search_ms": search_ms, "total_ms": total_ms}
        logger.debug("hybrid_search_timing", **timing, endpoint="hybrid_search_legacy")

        data = {"results": results}
        if req.include_timing:
            data["timing_ms"] = timing
        return success_response(data)
    except (CollectionNotFoundError, DimensionMismatchError) as e:
        return error_response(400, str(e))
