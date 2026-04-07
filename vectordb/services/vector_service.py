# vectordb/services/vector_service.py
import numpy as np
import structlog

from vectordb.indexing.hnsw import HNSWIndexer

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Vector encode/decode (binary BLOB storage)
# ------------------------------------------------------------------
def encode_vector(vec: np.ndarray) -> bytes:
    """Convert a numpy float32 vector to bytes for BLOB storage."""
    return vec.astype(np.float32).tobytes()


def decode_vector(blob: bytes) -> np.ndarray:
    """Convert bytes from BLOB storage back to a numpy float32 vector."""
    return np.frombuffer(blob, dtype=np.float32).copy()


# ------------------------------------------------------------------
# Vector normalization
# ------------------------------------------------------------------
def normalize_vector(vec: np.ndarray) -> np.ndarray:
    """L2-normalize a vector for cosine similarity."""
    return vec / (np.linalg.norm(vec) + 1e-10)


# ------------------------------------------------------------------
# Index helpers
# ------------------------------------------------------------------
def safe_add_to_index(indexer: HNSWIndexer, vector: np.ndarray, internal_id: int):
    """Add a vector to the HNSW index, resizing if necessary."""
    try:
        indexer.add_item(vector, internal_id)
    except RuntimeError as e:
        logger.warning("index_full_resizing", error=str(e))
        current_max = indexer.index.get_max_elements()
        indexer.index.resize_index(current_max * 2)
        indexer.add_item(vector, internal_id)


# ------------------------------------------------------------------
# Response helpers
# ------------------------------------------------------------------
def success_response(data):
    return {"status": "success", "data": data, "error": None}


def error_response(code, message):
    return {"status": "error", "data": None, "error": {"code": code, "message": message}}
