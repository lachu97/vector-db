"""Graph RAG endpoints — /v1/collections/{name}/graph/..."""
import time
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vectordb.auth import ApiKeyInfo, require_pro_or_scale, require_scale
from vectordb.backends import get_backend
from vectordb.backends.base import VectorBackend
from vectordb.models.db import get_db
from vectordb.models.schemas import (
    GraphCommunity,
    GraphEntityResult,
    GraphPathRequest,
    GraphPathResponse,
    GraphPathStep,
    GraphRelation,
    GraphSearchRequest,
    GraphSearchResponse,
    GraphSummarizeRequest,
    GraphSummarizeResponse,
)
from vectordb.services.graph_manager import graph_manager
from vectordb.services.graph_retrieval import community_detection, path_analysis
from vectordb.services.vector_service import error_response, success_response

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/collections", tags=["graph"])


@router.get("/{name}/graph/status")
async def graph_status(
    name: str,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_pro_or_scale),
):
    """Return job queue stats plus entity/edge counts for the collection's graph."""
    col = await backend.get_collection(name, user_id=auth.user_id)
    if not col:
        return error_response(404, f"Collection '{name}' not found")

    db: Session = next(get_db())
    try:
        stats = await graph_manager.get_job_stats(col["id"], db)
        entity_count, edge_count = await graph_manager.get_counts(col["id"], db)
    finally:
        db.close()

    return success_response({
        "jobs": stats,
        "entity_count": entity_count,
        "edge_count": edge_count,
    })


@router.post("/{name}/graph/search")
async def graph_search(
    name: str,
    req: GraphSearchRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_pro_or_scale),
):
    """Fuzzy text search over graph entities, returning matched nodes with relations."""
    col = await backend.get_collection(name, user_id=auth.user_id)
    if not col:
        return error_response(404, f"Collection '{name}' not found")

    db: Session = next(get_db())
    try:
        t0 = time.perf_counter()
        graph = await graph_manager.get_graph(col["id"], db)
        search_ms = round((time.perf_counter() - t0) * 1000, 2)
    finally:
        db.close()

    # Tokenise query for fuzzy matching
    query_words = [w for w in req.query.lower().split() if w]

    results: List[GraphEntityResult] = []
    for node_id, node_data in graph.nodes(data=True):
        entity_text: str = node_data.get("entity_text", "")
        entity_text_lower = entity_text.lower()

        # Skip if no query word matches
        if not any(word in entity_text_lower for word in query_words):
            continue

        # Optional entity_type filter
        entity_type: Optional[str] = node_data.get("entity_type")
        if req.entity_types and entity_type not in req.entity_types:
            continue

        # Build relations from outgoing edges
        relations: List[GraphRelation] = []
        for _src, tgt, _key, edge_data in graph.edges(node_id, keys=True, data=True):
            tgt_data = graph.nodes.get(tgt, {})
            relations.append(GraphRelation(
                relation_type=edge_data.get("relation_type", "related_to"),
                target_entity=tgt_data.get("entity_text", str(tgt)),
                target_type=tgt_data.get("entity_type"),
                weight=float(edge_data.get("weight", 1.0)),
            ))

        # chunk_ids: node stores a single chunk_id; collect it
        chunk_id = node_data.get("chunk_id")
        chunk_ids = [chunk_id] if chunk_id else []

        results.append(GraphEntityResult(
            entity_text=entity_text,
            entity_type=entity_type,
            relations=relations,
            chunk_ids=chunk_ids,
        ))

        if len(results) >= req.k:
            break

    response = GraphSearchResponse(
        entities=results,
        timing_ms={"search_ms": search_ms},
    )
    return success_response(response.model_dump())


@router.post("/{name}/graph/path")
async def graph_path(
    name: str,
    req: GraphPathRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_pro_or_scale),
):
    """Find shortest paths between two entities in the collection's knowledge graph."""
    col = await backend.get_collection(name, user_id=auth.user_id)
    if not col:
        return error_response(404, f"Collection '{name}' not found")

    db = next(get_db())
    try:
        t0 = time.perf_counter()
        graph = await graph_manager.get_graph(col["id"], db)
        result = path_analysis(graph, req.source, req.target, max_hops=req.max_hops)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    finally:
        db.close()

    # Convert raw step dicts to GraphPathStep objects
    formatted_paths = [
        [GraphPathStep(**step) for step in path]
        for path in result["paths"]
    ]

    response = GraphPathResponse(
        source=result["source"],
        target=result["target"],
        paths=formatted_paths,
        path_count=result["path_count"],
        shortest_hop_count=result.get("shortest_hop_count"),
        timing_ms={"path_ms": elapsed_ms},
    )
    return success_response(response.model_dump())


@router.post("/{name}/graph/summarize")
async def graph_summarize(
    name: str,
    req: GraphSummarizeRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_scale),   # Scale only
):
    """Detect communities in the collection's knowledge graph using Louvain algorithm."""
    col = await backend.get_collection(name, user_id=auth.user_id)
    if not col:
        return error_response(404, f"Collection '{name}' not found")

    db = next(get_db())
    try:
        t0 = time.perf_counter()
        graph = await graph_manager.get_graph(col["id"], db)
        communities_raw = community_detection(graph, max_communities=req.max_communities)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    finally:
        db.close()

    communities = [GraphCommunity(**c) for c in communities_raw]
    response = GraphSummarizeResponse(
        communities=communities,
        total_communities=len(communities),
        timing_ms={"summarize_ms": elapsed_ms},
    )
    return success_response(response.model_dump())
