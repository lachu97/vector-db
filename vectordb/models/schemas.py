# vectordb/models/schemas.py
from pydantic import BaseModel, model_validator
from typing import List, Optional, Dict, Any


# ------------------------------------------------------------------
# Collection schemas
# ------------------------------------------------------------------
class CreateCollectionRequest(BaseModel):
    name: str
    dim: int
    distance_metric: str = "cosine"
    description: Optional[str] = None


class UpdateCollectionRequest(BaseModel):
    description: Optional[str] = None  # cosine, l2, ip


# ------------------------------------------------------------------
# Vector schemas
# ------------------------------------------------------------------
class UpsertRequest(BaseModel):
    external_id: str
    vector: Optional[List[float]] = None
    text: Optional[str] = None       # auto-embedded via embedding_service
    metadata: Optional[Dict[str, Any]] = None
    content: Optional[str] = None    # optional text for hybrid word search
    include_timing: bool = False

    @model_validator(mode="after")
    def require_vector_or_text(self):
        if not self.vector and not self.text:
            raise ValueError("Either 'vector' or 'text' must be provided")
        return self


class BulkUpsertRequest(BaseModel):
    items: List[UpsertRequest]
    include_timing: bool = False


# ------------------------------------------------------------------
# Search schemas
# ------------------------------------------------------------------
class SearchRequest(BaseModel):
    vector: Optional[List[float]] = None
    text: Optional[str] = None       # auto-embedded via embedding_service
    k: int = 10
    offset: int = 0
    filters: Optional[Dict[str, Any]] = None
    include_timing: bool = False

    @model_validator(mode="after")
    def require_vector_or_text(self):
        if not self.vector and not self.text:
            raise ValueError("Either 'vector' or 'text' must be provided")
        return self


# ------------------------------------------------------------------
# Batch delete schemas
# ------------------------------------------------------------------
class BatchDeleteRequest(BaseModel):
    external_ids: List[str]


# ------------------------------------------------------------------
# Rerank schemas
# ------------------------------------------------------------------
class RerankRequest(BaseModel):
    vector: Optional[List[float]] = None
    text: Optional[str] = None       # auto-embedded via embedding_service
    candidates: List[str]            # list of external_ids to re-score
    include_timing: bool = False

    @model_validator(mode="after")
    def require_vector_or_text(self):
        if not self.vector and not self.text:
            raise ValueError("Either 'vector' or 'text' must be provided")
        return self


# ------------------------------------------------------------------
# Hybrid search schemas
# ------------------------------------------------------------------
class HybridSearchRequest(BaseModel):
    query_text: str
    vector: Optional[List[float]] = None  # auto-embedded from query_text if absent
    k: int = 10
    offset: int = 0
    alpha: float = 0.5  # weight for vector score (1-alpha for text score)
    filters: Optional[Dict[str, Any]] = None
    include_timing: bool = False


# ------------------------------------------------------------------
# RAG query schemas
# ------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str
    collection_name: str
    top_k: int = 5
    filters: Optional[Dict[str, Any]] = None
    include_timing: bool = False
