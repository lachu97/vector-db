# vectordb/routers/vectors.py
import time

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
from vectordb.models.schemas import BulkUpsertRequest, BatchDeleteRequest, UpsertRequest
from vectordb.services.embedding_service import embed_text, embed_batch
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

async def _check_collection_access(backend, collection_name, user_id):
    """Verify the user has access to this collection. Returns error response or None."""
    col = await backend.get_collection(collection_name, user_id=user_id)
    if not col:
        return error_response(404, f"Collection '{collection_name}' not found")
    return None


@router.post("/collections/{collection_name}/upsert")
async def upsert_vector_in_collection(
    collection_name: str,
    item: UpsertRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    t_start = time.perf_counter()
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err
    settings = _settings()
    metadata = item.metadata or {}
    if len(metadata) > settings.max_metadata_size:
        return error_response(400, f"Metadata exceeds maximum of {settings.max_metadata_size} keys")

    # Resolve text → vector via embedding_service
    vector = item.vector
    content = item.content
    embedding_ms = 0.0
    if not vector and item.text:
        t0 = time.perf_counter()
        vector = embed_text(item.text)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)
        if not content:
            content = item.text

    try:
        t_storage = time.perf_counter()
        result = await backend.upsert(
            collection_name,
            item.external_id,
            vector,
            metadata or None,
            content,
        )
        storage_ms = round((time.perf_counter() - t_storage) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "storage_ms": storage_ms, "total_ms": total_ms}
        logger.debug("upsert_timing", **timing, endpoint="upsert")

        if item.include_timing:
            result["timing_ms"] = timing
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
    t_start = time.perf_counter()
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err
    settings = _settings()
    if len(req.items) > settings.max_batch_size:
        return error_response(400, f"Batch size exceeds maximum of {settings.max_batch_size}")
    for it in req.items:
        if it.metadata and len(it.metadata) > settings.max_metadata_size:
            return error_response(
                400, f"Metadata for '{it.external_id}' exceeds maximum of {settings.max_metadata_size} keys"
            )

    # Batch-embed items that have text but no vector
    embedding_ms = 0.0
    text_indices = [i for i, it in enumerate(req.items) if not it.vector and it.text]
    if text_indices:
        t0 = time.perf_counter()
        texts_to_embed = [req.items[i].text for i in text_indices]
        embeddings = embed_batch(texts_to_embed)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)
    else:
        embeddings = []

    try:
        items = []
        embed_idx = 0
        for it in req.items:
            vector = it.vector
            content = it.content
            if not vector and it.text:
                vector = embeddings[embed_idx]
                embed_idx += 1
                if not content:
                    content = it.text
            items.append({
                "external_id": it.external_id, "vector": vector,
                "metadata": it.metadata, "content": content,
            })
        t_storage = time.perf_counter()
        results = await backend.bulk_upsert(collection_name, items)
        storage_ms = round((time.perf_counter() - t_storage) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "storage_ms": storage_ms, "total_ms": total_ms}
        logger.debug("bulk_upsert_timing", **timing, endpoint="bulk_upsert", count=len(req.items))

        data = {"results": results}
        if req.include_timing:
            data["timing_ms"] = timing
        return success_response(data)
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
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err
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
    access_err = await _check_collection_access(backend, collection_name, auth.user_id)
    if access_err:
        return access_err
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
    item: UpsertRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    t_start = time.perf_counter()
    await _ensure_default(backend)
    settings = _settings()
    metadata = item.metadata or {}
    if len(metadata) > settings.max_metadata_size:
        return error_response(400, f"Metadata exceeds maximum of {settings.max_metadata_size} keys")

    # Resolve text → vector
    vector = item.vector
    content = item.content
    embedding_ms = 0.0
    if not vector and item.text:
        t0 = time.perf_counter()
        vector = embed_text(item.text)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)
        if not content:
            content = item.text

    try:
        t_storage = time.perf_counter()
        result = await backend.upsert(
            DEFAULT_COLLECTION,
            item.external_id,
            vector,
            metadata or None,
            content,
        )
        storage_ms = round((time.perf_counter() - t_storage) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "storage_ms": storage_ms, "total_ms": total_ms}
        logger.debug("upsert_timing", **timing, endpoint="upsert_legacy")

        if item.include_timing:
            result["timing_ms"] = timing
        return success_response(result)
    except (CollectionNotFoundError, DimensionMismatchError) as e:
        return error_response(400, str(e))


@router.post("/bulk_upsert")
async def bulk_upsert_legacy(
    req: BulkUpsertRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    t_start = time.perf_counter()
    settings = _settings()
    if len(req.items) > settings.max_batch_size:
        return error_response(400, f"Batch size exceeds maximum of {settings.max_batch_size}")
    await _ensure_default(backend)

    # Batch-embed items that have text but no vector
    embedding_ms = 0.0
    text_indices = [i for i, it in enumerate(req.items) if not it.vector and it.text]
    if text_indices:
        t0 = time.perf_counter()
        texts_to_embed = [req.items[i].text for i in text_indices]
        embeddings = embed_batch(texts_to_embed)
        embedding_ms = round((time.perf_counter() - t0) * 1000, 2)
    else:
        embeddings = []

    try:
        items = []
        embed_idx = 0
        for it in req.items:
            vector = it.vector
            content = it.content
            if not vector and it.text:
                vector = embeddings[embed_idx]
                embed_idx += 1
                if not content:
                    content = it.text
            items.append({
                "external_id": it.external_id, "vector": vector,
                "metadata": it.metadata, "content": content,
            })
        t_storage = time.perf_counter()
        results = await backend.bulk_upsert(DEFAULT_COLLECTION, items)
        storage_ms = round((time.perf_counter() - t_storage) * 1000, 2)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        timing = {"embedding_ms": embedding_ms, "storage_ms": storage_ms, "total_ms": total_ms}
        logger.debug("bulk_upsert_timing", **timing, endpoint="bulk_upsert_legacy", count=len(req.items))

        data = {"results": results}
        if req.include_timing:
            data["timing_ms"] = timing
        return success_response(data)
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
