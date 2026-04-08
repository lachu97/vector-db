# vectordb/models/schemas.py
from pydantic import BaseModel
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
    vector: List[float]
    metadata: Optional[Dict[str, Any]] = None
    content: Optional[str] = None  # optional text for hybrid search


class BulkUpsertRequest(BaseModel):
    items: List[UpsertRequest]


# ------------------------------------------------------------------
# Search schemas
# ------------------------------------------------------------------
class SearchRequest(BaseModel):
    vector: List[float]
    k: int = 10
    offset: int = 0
    filters: Optional[Dict[str, Any]] = None


# ------------------------------------------------------------------
# Batch delete schemas
# ------------------------------------------------------------------
class BatchDeleteRequest(BaseModel):
    external_ids: List[str]


# ------------------------------------------------------------------
# Rerank schemas
# ------------------------------------------------------------------
class RerankRequest(BaseModel):
    vector: List[float]
    candidates: List[str]  # list of external_ids to re-score


# ------------------------------------------------------------------
# Hybrid search schemas
# ------------------------------------------------------------------
class HybridSearchRequest(BaseModel):
    query_text: str
    vector: List[float]
    k: int = 10
    offset: int = 0
    alpha: float = 0.5  # weight for vector score (1-alpha for text score)
    filters: Optional[Dict[str, Any]] = None
