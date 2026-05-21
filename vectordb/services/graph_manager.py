"""
GraphManager — per-collection networkx.MultiDiGraph, lazy-loaded from SQLite.

Design:
- _graphs: Dict[collection_id → MultiDiGraph], in-memory cache
- _locks: Dict[collection_id → asyncio.Lock], prevents concurrent mutation
- Lazy load: graph only loaded from DB on first get_graph() call
- Invalidate: del _graphs[collection_id], forces reload on next access
- Zero startup cost: nothing rebuilt at startup
"""
import asyncio
from typing import Dict, List, Optional, Tuple
import networkx as nx
from sqlalchemy.orm import Session

from vectordb.models.db import GraphEntity, GraphEdge, get_db


class GraphManager:
    def __init__(self):
        self._graphs: Dict[int, nx.MultiDiGraph] = {}
        self._locks: Dict[int, asyncio.Lock] = {}

    def _get_lock(self, collection_id: int) -> asyncio.Lock:
        if collection_id not in self._locks:
            self._locks[collection_id] = asyncio.Lock()
        return self._locks[collection_id]

    def _load_graph_from_db(self, collection_id: int, db: Session) -> nx.MultiDiGraph:
        """Load entities + edges from SQLite, build MultiDiGraph. Called under lock."""
        G = nx.MultiDiGraph()
        entities = db.query(GraphEntity).filter_by(collection_id=collection_id).all()
        for e in entities:
            G.add_node(e.id, entity_text=e.entity_text, entity_type=e.entity_type,
                       chunk_id=e.chunk_id, vector_external_id=e.vector_external_id,
                       document_id=e.document_id)
        edges = db.query(GraphEdge).filter_by(collection_id=collection_id).all()
        for edge in edges:
            G.add_edge(edge.source_entity_id, edge.target_entity_id,
                       relation_type=edge.relation_type, weight=edge.weight,
                       document_id=edge.document_id, chunk_id=edge.chunk_id)
        return G

    async def get_graph(self, collection_id: int, db: Session) -> nx.MultiDiGraph:
        """Lazy load from SQLite on first access, then cache in memory."""
        if collection_id in self._graphs:
            return self._graphs[collection_id]
        async with self._get_lock(collection_id):
            # Double-check after acquiring lock
            if collection_id not in self._graphs:
                loop = asyncio.get_event_loop()
                G = await loop.run_in_executor(None, self._load_graph_from_db, collection_id, db)
                self._graphs[collection_id] = G
        return self._graphs[collection_id]

    async def invalidate_graph(self, collection_id: int):
        """Force reload on next get_graph() call."""
        self._graphs.pop(collection_id, None)

    async def add_entities_edges(
        self,
        collection_id: int,
        db: Session,
        entities: List[dict],   # list of dicts matching GraphEntity columns
        edges: List[dict],       # list of dicts matching GraphEdge columns
    ):
        """
        Insert entities + edges to SQLite, then invalidate in-memory graph.
        entities: [{"entity_text": str, "entity_type": str, "document_id": str,
                    "chunk_id": str, "vector_external_id": str|None,
                    "extractor_version": str, "model_name": str,
                    "extraction_prompt_hash": str|None}]
        edges: [{"source_entity_text": str, "target_entity_text": str,
                 "relation_type": str, "weight": float,
                 "document_id": str, "chunk_id": str,
                 "extractor_version": str, "model_name": str}]

        NOTE: edges use entity_text to reference entities (resolved to entity IDs here).
        """
        # Insert entities
        entity_text_to_id: Dict[str, int] = {}
        for e_dict in entities:
            entity = GraphEntity(collection_id=collection_id, **e_dict)
            db.add(entity)
            db.flush()  # get the auto-generated id
            entity_text_to_id[e_dict["entity_text"].lower()] = entity.id

        # Also look up existing entities in this collection for edge resolution
        existing = db.query(GraphEntity.id, GraphEntity.entity_text).filter_by(
            collection_id=collection_id).all()
        for eid, etext in existing:
            entity_text_to_id.setdefault(etext.lower(), eid)

        # Insert edges (resolve text → id)
        for edge_dict in edges:
            src_id = entity_text_to_id.get(edge_dict["source_entity_text"].lower())
            tgt_id = entity_text_to_id.get(edge_dict["target_entity_text"].lower())
            if src_id is None or tgt_id is None:
                continue  # skip unresolvable edges
            edge = GraphEdge(
                collection_id=collection_id,
                source_entity_id=src_id,
                target_entity_id=tgt_id,
                relation_type=edge_dict["relation_type"],
                weight=edge_dict.get("weight", 1.0),
                document_id=edge_dict["document_id"],
                chunk_id=edge_dict["chunk_id"],
                extractor_version=edge_dict["extractor_version"],
                model_name=edge_dict["model_name"],
            )
            db.add(edge)

        db.commit()
        await self.invalidate_graph(collection_id)

    async def delete_by_document(self, collection_id: int, document_id: str, db: Session):
        """Cascade delete all entities + edges for a document, then invalidate."""
        # Delete edges first (FK constraint)
        entity_ids = [
            row[0] for row in
            db.query(GraphEntity.id).filter_by(
                collection_id=collection_id, document_id=document_id).all()
        ]
        if entity_ids:
            db.query(GraphEdge).filter(
                GraphEdge.document_id == document_id,
                GraphEdge.collection_id == collection_id,
            ).delete(synchronize_session=False)
            db.query(GraphEntity).filter(
                GraphEntity.document_id == document_id,
                GraphEntity.collection_id == collection_id,
            ).delete(synchronize_session=False)
            db.commit()
        await self.invalidate_graph(collection_id)

    async def get_job_stats(self, collection_id: int, db: Session) -> dict:
        """Return job counts by status for a collection."""
        from sqlalchemy import func as sqlfunc
        from vectordb.models.db import GraphExtractionJob
        rows = db.query(
            GraphExtractionJob.status,
            sqlfunc.count(GraphExtractionJob.id)
        ).filter_by(collection_id=collection_id).group_by(GraphExtractionJob.status).all()
        counts = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
        for status, count in rows:
            counts[status] = count
        return counts

    async def get_counts(self, collection_id: int, db: Session) -> Tuple[int, int]:
        """Return (entity_count, edge_count) for a collection."""
        entity_count = db.query(GraphEntity).filter_by(collection_id=collection_id).count()
        edge_count = db.query(GraphEdge).filter_by(collection_id=collection_id).count()
        return entity_count, edge_count


# Module-level singleton
graph_manager = GraphManager()
