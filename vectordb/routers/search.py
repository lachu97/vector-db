# vectordb/routers/search.py
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
from vectordb.models.schemas import HybridSearchRequest, RerankRequest, SearchRequest
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

@router.post("/collections/{collection_name}/search")
async def search_in_collection(
    collection_name: str,
    req: SearchRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    try:
        results = await backend.search(collection_name, req.vector, req.k, req.offset, req.filters)
        return success_response({"results": results})
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
    try:
        results = await backend.rerank(collection_name, req.vector, req.candidates)
        return success_response({"results": results})
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
    if not (0.0 <= req.alpha <= 1.0):
        return error_response(400, "alpha must be between 0.0 and 1.0")
    try:
        results = await backend.hybrid_search(
            collection_name, req.query_text, req.vector, req.k, req.offset, req.alpha, req.filters
        )
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
    await _ensure_default(backend)
    try:
        results = await backend.search(DEFAULT_COLLECTION, req.vector, req.k, req.offset, req.filters)
        return success_response({"results": results})
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
    await _ensure_default(backend)
    try:
        results = await backend.rerank(DEFAULT_COLLECTION, req.vector, req.candidates)
        return success_response({"results": results})
    except (CollectionNotFoundError, DimensionMismatchError) as e:
        return error_response(400, str(e))


@router.post("/hybrid_search")
async def hybrid_search_legacy(
    req: HybridSearchRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    if not (0.0 <= req.alpha <= 1.0):
        return error_response(400, "alpha must be between 0.0 and 1.0")
    await _ensure_default(backend)
    try:
        results = await backend.hybrid_search(
            DEFAULT_COLLECTION, req.query_text, req.vector, req.k, req.offset, req.alpha, req.filters
        )
        return success_response({"results": results})
    except (CollectionNotFoundError, DimensionMismatchError) as e:
        return error_response(400, str(e))
