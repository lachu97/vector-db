# vectordb/services/document_service.py
"""Document processing: chunk text, embed, store in vector DB."""
import time
import uuid
from typing import Dict, Any, Tuple

import structlog

from vectordb.backends.base import VectorBackend
from vectordb.services.chunking import chunk_text
from vectordb.services.embedding_service import embed_batch

logger = structlog.get_logger(__name__)


async def process_document(
    file_text: str,
    collection_name: str,
    backend: VectorBackend,
    chunk_size: int = 500,
    overlap: int = 50,
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """Chunk text, generate embeddings, and bulk-upsert into existing collection.

    Returns (result_dict, timing_dict).
    """
    t0 = time.perf_counter()
    document_id = str(uuid.uuid4())

    # 1. Chunk
    chunks = chunk_text(file_text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        timing = {"embedding_ms": 0, "storage_ms": 0, "total_ms": 0}
        return {"document_id": document_id, "chunks_created": 0}, timing

    # 2. Embed all chunks in one batch call
    t_embed_start = time.perf_counter()
    embeddings = embed_batch(chunks)
    t_embed = time.perf_counter()

    # 3. Build bulk-upsert items
    items = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        items.append({
            "external_id": f"{document_id}:{i}",
            "vector": embedding,
            "metadata": {
                "document_id": document_id,
                "chunk_index": i,
                "text": chunk,
            },
            "content": chunk,  # for hybrid search
        })

    # 4. Use existing bulk_upsert
    t_storage_start = time.perf_counter()
    await backend.bulk_upsert(collection_name, items)
    t_storage = time.perf_counter()

    timing = {
        "embedding_ms": round((t_embed - t_embed_start) * 1000, 2),
        "storage_ms": round((t_storage - t_storage_start) * 1000, 2),
        "total_ms": round((t_storage - t0) * 1000, 2),
    }

    logger.info(
        "document_processed",
        document_id=document_id,
        collection=collection_name,
        chunks=len(chunks),
        **timing,
    )

    return {"document_id": document_id, "chunks_created": len(chunks)}, timing
