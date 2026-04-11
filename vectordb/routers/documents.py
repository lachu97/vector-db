# vectordb/routers/documents.py
"""POST /v1/documents/upload — multipart file upload for RAG."""
import structlog
from fastapi import APIRouter, Depends, File, Form, UploadFile

from vectordb.auth import ApiKeyInfo, require_readwrite
from vectordb.backends import get_backend
from vectordb.backends.base import CollectionNotFoundError, DimensionMismatchError, VectorBackend
from vectordb.config import get_settings
from vectordb.services.document_service import process_document
from vectordb.services.vector_service import error_response, success_response

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    collection_name: str = Form(...),
    file: UploadFile = File(...),
    include_timing: bool = Form(False),
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readwrite),
):
    settings = get_settings()

    # Validate file
    if not file.filename:
        return error_response(400, "No file provided")
    if not file.filename.endswith(".txt"):
        return error_response(400, "Only .txt files are supported")

    # Validate collection exists and user has access
    col = await backend.get_collection(collection_name, user_id=auth.user_id)
    if not col:
        return error_response(404, f"Collection '{collection_name}' not found")

    # Read file content
    content = await file.read()
    try:
        file_text = content.decode("utf-8")
    except UnicodeDecodeError:
        return error_response(400, "File must be valid UTF-8 text")

    if not file_text.strip():
        return error_response(400, "File is empty")

    # Process document
    try:
        result, timing = await process_document(
            file_text,
            collection_name,
            backend,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
            user_id=auth.user_id,
        )
        if include_timing:
            result["timing_ms"] = timing
        return success_response(result)
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{collection_name}' not found")
    except DimensionMismatchError as e:
        return error_response(400, str(e))
