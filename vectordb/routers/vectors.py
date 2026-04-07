# vectordb/routers/vectors.py
import structlog
from fastapi import APIRouter, Depends

from vectordb.auth import ApiKeyInfo, require_readwrite
from vectordb.backends import get_backend
from vectordb.backends.base import (
    CollectionNotFoundError,
    DimensionMismatchError,
    VectorNotFoundError,
    VectorBackend,
)
from vectordb.config import get_settings
from vectordb.models.schemas import BulkUpsertRequest, BatchDeleteRequest
from vectordb.services.vector_service import error_response, success_response

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["vectors"])

DEFAULT_COLLECTION = "default"


def _settings():
    return get_settings()


async def _ensure_default(backend: VectorBackend):
    """Get or create the default collection for legacy endpoints."""
    if hasattr(backend, "ensure_default_collection"):
        return await backend.ensure_default_collection()
    col = await backend.get_collection(DEFAULT_COLLECTION)
    if col:
        return col
    from vectordb.backends.base import CollectionAlreadyExistsError
    try:
        return await backend.create_collection(
            DEFAULT_COLLECTION, get_settings().vector_dim, "cosine"
        )
    except CollectionAlreadyExistsError:
        return await backend.get_collection(DEFAULT_COLLECTION)


# ------------------------------------------------------------------
# Collection-scoped endpoints
# ------------------------------------------------------------------

@router.post("/collections/{collection_name}/upsert")
async def upsert_vector_in_collection(
    collection_name: str,
    item: dict,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    settings = _settings()
    metadata = item.get("metadata") or {}
    if len(metadata) > settings.max_metadata_size:
        return error_response(400, f"Metadata exceeds maximum of {settings.max_metadata_size} keys")
    try:
        result = await backend.upsert(
            collection_name,
            item.get("external_id", ""),
            item.get("vector", []),
            metadata or None,
            item.get("content"),
        )
        return success_response(result)
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except DimensionMismatchError as e:
        return error_response(400, str(e))


@router.post("/collections/{collection_name}/bulk_upsert")
async def bulk_upsert_in_collection(
    collection_name: str,
    req: BulkUpsertRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    settings = _settings()
    if len(req.items) > settings.max_batch_size:
        return error_response(400, f"Batch size exceeds maximum of {settings.max_batch_size}")
    for it in req.items:
        if it.metadata and len(it.metadata) > settings.max_metadata_size:
            return error_response(
                400, f"Metadata for '{it.external_id}' exceeds maximum of {settings.max_metadata_size} keys"
            )
    try:
        items = [
            {"external_id": it.external_id, "vector": it.vector,
             "metadata": it.metadata, "content": it.content}
            for it in req.items
        ]
        results = await backend.bulk_upsert(collection_name, items)
        return success_response({"results": results})
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except DimensionMismatchError as e:
        return error_response(400, str(e))


@router.delete("/collections/{collection_name}/delete/{external_id}")
async def delete_vector_in_collection(
    collection_name: str,
    external_id: str,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    try:
        result = await backend.delete_vector(collection_name, external_id)
        return success_response(result)
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except VectorNotFoundError:
        return error_response(404, "Not found")


@router.post("/collections/{collection_name}/delete_batch")
async def batch_delete_in_collection(
    collection_name: str,
    req: BatchDeleteRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    settings = _settings()
    if len(req.external_ids) > settings.max_batch_size:
        return error_response(400, f"Batch size exceeds maximum of {settings.max_batch_size}")
    try:
        result = await backend.batch_delete(collection_name, req.external_ids)
        return success_response(result)
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")


# ------------------------------------------------------------------
# Legacy endpoints (route to "default" collection)
# ------------------------------------------------------------------

@router.post("/upsert")
async def upsert_vector_legacy(
    item: dict,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    await _ensure_default(backend)
    settings = _settings()
    metadata = item.get("metadata") or {}
    if len(metadata) > settings.max_metadata_size:
        return error_response(400, f"Metadata exceeds maximum of {settings.max_metadata_size} keys")
    try:
        result = await backend.upsert(
            DEFAULT_COLLECTION,
            item.get("external_id", ""),
            item.get("vector", []),
            metadata or None,
            item.get("content"),
        )
        return success_response(result)
    except (CollectionNotFoundError, DimensionMismatchError) as e:
        return error_response(400, str(e))


@router.post("/bulk_upsert")
async def bulk_upsert_legacy(
    req: BulkUpsertRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    settings = _settings()
    if len(req.items) > settings.max_batch_size:
        return error_response(400, f"Batch size exceeds maximum of {settings.max_batch_size}")
    await _ensure_default(backend)
    try:
        items = [
            {"external_id": it.external_id, "vector": it.vector,
             "metadata": it.metadata, "content": it.content}
            for it in req.items
        ]
        results = await backend.bulk_upsert(DEFAULT_COLLECTION, items)
        return success_response({"results": results})
    except (CollectionNotFoundError, DimensionMismatchError) as e:
        return error_response(400, str(e))


@router.delete("/delete/{external_id}")
async def delete_vector_legacy(
    external_id: str,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    await _ensure_default(backend)
    try:
        result = await backend.delete_vector(DEFAULT_COLLECTION, external_id)
        return success_response(result)
    except VectorNotFoundError:
        return error_response(404, "Not found")
    except CollectionNotFoundError:
        return error_response(404, "Not found")
