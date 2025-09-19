# schemas.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class UpsertRequest(BaseModel):
    external_id: str
    vector: List[float]
    metadata: Optional[Dict[str, Any]] = None

class BulkUpsertRequest(BaseModel):
    items: List[UpsertRequest]

class SearchRequest(BaseModel):
    vector: List[float]
    k: int = 10
    filters: Optional[Dict[str, Any]] = None
