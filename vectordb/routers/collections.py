# vectordb/routers/collections.py
import structlog
from fastapi import APIRouter, Depends

from vectordb.auth import ApiKeyInfo, require_admin, require_readonly
from vectordb.backends import get_backend
from vectordb.backends.base import (
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    VectorBackend,
)
from vectordb.config import get_settings
from vectordb.models.schemas import CreateCollectionRequest
from vectordb.services.vector_service import error_response, success_response

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/collections", tags=["collections"])

VALID_METRICS = {"cosine", "l2", "ip"}


@router.post("")
async def create_collection(
    req: CreateCollectionRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_admin),
):
    settings = get_settings()
    if req.distance_metric not in VALID_METRICS:
        return error_response(400, f"Invalid distance_metric. Must be one of: {', '.join(VALID_METRICS)}")
    if req.dim < 1:
        return error_response(400, "Dimension must be at least 1")
    if req.dim > settings.max_vector_dim:
        return error_response(400, f"Dimension must not exceed {settings.max_vector_dim}")

    try:
        col = await backend.create_collection(req.name, req.dim, req.distance_metric)
        return success_response(col)
    except CollectionAlreadyExistsError:
        return error_response(409, f"Collection '{req.name}' already exists")


@router.get("")
async def list_collections(
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    cols = await backend.list_collections()
    return success_response({"collections": cols})


@router.get("/{name}")
async def get_collection(
    name: str,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    col = await backend.get_collection(name)
    if not col:
        return error_response(404, f"Collection '{name}' not found")
    return success_response(col)


@router.delete("/{name}")
async def delete_collection(
    name: str,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_admin),
):
    try:
        await backend.delete_collection(name)
        return success_response({"status": "deleted", "name": name})
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{name}' not found")
