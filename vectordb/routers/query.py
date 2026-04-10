# vectordb/routers/query.py
"""POST /v1/query — RAG query retrieval. POST /v1/ask — RAG answer generation."""
import structlog
from fastapi import APIRouter, Depends

from vectordb.auth import ApiKeyInfo, require_readonly
from vectordb.backends import get_backend
from vectordb.backends.base import CollectionNotFoundError, VectorBackend
from vectordb.config import get_settings
from vectordb.models.schemas import AskRequest, QueryRequest
from vectordb.services.query_service import run_query
from vectordb.services.vector_service import error_response, success_response

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["query"])


@router.post("/query")
async def query_documents(
    req: QueryRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    settings = get_settings()

    # Validate query length
    if len(req.query) > settings.max_query_length:
        return error_response(
            400, f"Query exceeds maximum length of {settings.max_query_length} characters"
        )

    if not req.query.strip():
        return error_response(400, "Query cannot be empty")

    # Validate collection exists and user has access
    col = await backend.get_collection(req.collection_name, user_id=auth.user_id)
    if not col:
        return error_response(404, f"Collection '{req.collection_name}' not found")

    # Run query
    try:
        results, timing = await run_query(
            req.query, req.collection_name, req.top_k, backend, filters=req.filters,
        )
        data = {
            "query": req.query,
            "collection": req.collection_name,
            "results": results,
        }
        if req.include_timing:
            data["timing_ms"] = timing
        return success_response(data)
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{req.collection_name}' not found")


@router.post("/ask")
async def ask(
    req: AskRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    settings = get_settings()

    if len(req.query) > settings.max_query_length:
        return error_response(
            400, f"Query exceeds maximum length of {settings.max_query_length} characters"
        )

    # Validate collection exists and user has access
    col = await backend.get_collection(req.collection, user_id=auth.user_id)
    if not col:
        return error_response(404, f"Collection '{req.collection}' not found")

    # Retrieve sources using existing run_query
    try:
        results, _ = await run_query(req.query, req.collection, req.k, backend)
    except CollectionNotFoundError:
        return error_response(404, f"Collection '{req.collection}' not found")

    # No results — graceful response
    if not results:
        return success_response({"answer": "No relevant information found.", "sources": []})

    # Build context from text fields only (skip empty/None)
    texts = [r["text"] for r in results if r.get("text")]
    context = "\n\n".join(texts)[:3000]

    # Generate answer
    from vectordb.services.llm_service import generate_answer
    answer = await generate_answer(req.query, context)

    if not answer or not answer.strip():
        answer = "I couldn't generate a reliable answer from the available context."

    # Build sources
    sources = [
        {
            "external_id": r["external_id"],
            "score": r["score"],
            "content": r.get("text", ""),
            "metadata": r.get("metadata", {}),
        }
        for r in results
    ]

    return success_response({"answer": answer, "sources": sources})
