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


# ------------------------------------------------------------------
# Batch fetch schemas
# ------------------------------------------------------------------
class BatchFetchRequest(BaseModel):
    ids: List[str]
    include_vectors: bool = True

    @model_validator(mode="after")
    def validate_ids(self):
        if len(self.ids) > 100:
            raise ValueError("Maximum 100 IDs per request")
        return self


# ------------------------------------------------------------------
# Scroll schemas
# ------------------------------------------------------------------
class ScrollRequest(BaseModel):
    cursor: Optional[str] = None
    limit: int = 100
    filters: Optional[Dict[str, Any]] = None
    include_vectors: bool = True

    @model_validator(mode="after")
    def validate_limit(self):
        if self.limit < 1 or self.limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        return self


# ------------------------------------------------------------------
# Bulk search schemas
# ------------------------------------------------------------------
class BulkSearchQuery(BaseModel):
    vector: List[float]
    k: int = 10
    filters: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_vector(self):
        if len(self.vector) < 1:
            raise ValueError("vector must be non-empty")
        return self


class BulkSearchRequest(BaseModel):
    queries: List[BulkSearchQuery]

    @model_validator(mode="after")
    def validate_queries(self):
        if len(self.queries) > 20:
            raise ValueError("Maximum 20 queries per request")
        return self


# ------------------------------------------------------------------
# Ask (RAG answer generation) schemas
# ------------------------------------------------------------------
class AskRequest(BaseModel):
    query: str
    collection: str
    k: int = 5

    @model_validator(mode="after")
    def validate_ask(self):
        if not self.query.strip():
            raise ValueError("query must be non-empty")
        if self.k < 1 or self.k > 20:
            raise ValueError("k must be between 1 and 20")
        return self
