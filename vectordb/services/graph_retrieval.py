"""
Graph retrieval pipeline — modular functions for /graph/ask and graph endpoints.

Phase 2: path_analysis — shortest paths between entity pairs
Phase 3: community_detection — Louvain community detection
Phase 4: full 6-step retrieval pipeline (entity_retrieval, neighborhood_expansion,
         graph_reranking, context_assembly, graph_ask_pipeline)
"""
import asyncio
import networkx as nx
from typing import List, Dict, Optional, Any, Set


def find_entity_node(graph: nx.MultiDiGraph, entity_text: str) -> Optional[int]:
    """Find a node ID by exact or case-insensitive entity_text match."""
    entity_lower = entity_text.lower().strip()
    for node_id, data in graph.nodes(data=True):
        if data.get("entity_text", "").lower() == entity_lower:
            return node_id
    return None


def path_analysis(
    graph: nx.MultiDiGraph,
    source_text: str,
    target_text: str,
    max_hops: int = 4,
) -> Dict[str, Any]:
    """
    Find shortest paths between source and target entities in the graph.

    Returns:
        {
          "source": str,
          "target": str,
          "paths": [
            [{"entity": "Apple", "relation": "acquired", "entity_type": "ORG"}, ...]
          ],
          "path_count": int,
          "shortest_hop_count": int | None
        }

    Path format: alternating entity → relation → entity → relation → entity
    Each path is a list of step dicts. Entities have "entity" and "entity_type".
    Relation steps have "relation" and "weight".

    Falls back gracefully:
    - Returns empty paths if source or target not found
    - Returns empty paths if no path within max_hops
    - Handles disconnected graphs
    """
    result = {
        "source": source_text,
        "target": target_text,
        "paths": [],
        "path_count": 0,
        "shortest_hop_count": None,
    }

    src_id = find_entity_node(graph, source_text)
    tgt_id = find_entity_node(graph, target_text)

    if src_id is None or tgt_id is None:
        return result

    # nx.all_simple_paths returns node sequences
    # cutoff=max_hops limits hop count (edges, not nodes)
    try:
        raw_paths = list(nx.all_simple_paths(graph, src_id, tgt_id, cutoff=max_hops))
    except (nx.NetworkXError, nx.NodeNotFound):
        return result

    if not raw_paths:
        # try undirected (ignore direction)
        try:
            undirected = graph.to_undirected()
            raw_paths = list(nx.all_simple_paths(undirected, src_id, tgt_id, cutoff=max_hops))
        except Exception:
            return result

    # Convert node-sequence paths to human-readable step dicts
    formatted_paths = []
    for node_seq in raw_paths:
        steps = []
        for i, node_id in enumerate(node_seq):
            node_data = graph.nodes.get(node_id, {})
            steps.append({
                "entity": node_data.get("entity_text", str(node_id)),
                "entity_type": node_data.get("entity_type"),
            })
            if i < len(node_seq) - 1:
                next_id = node_seq[i + 1]
                # Get all edges between node_id → next_id, pick first (or best weight)
                edge_data_list = list(graph.get_edge_data(node_id, next_id, default={}).values())
                if not edge_data_list:
                    # try reverse direction (undirected fallback)
                    edge_data_list = [{"relation_type": "related_to", "weight": 1.0}]
                edge_data = edge_data_list[0] if edge_data_list else {}
                steps.append({
                    "relation": edge_data.get("relation_type", "related_to"),
                    "weight": float(edge_data.get("weight", 1.0)),
                })
        formatted_paths.append(steps)

    result["paths"] = formatted_paths
    result["path_count"] = len(formatted_paths)
    if formatted_paths:
        # shortest path in hops = (len(node_seq) - 1)
        result["shortest_hop_count"] = min(
            (len(p) - 1) // 2 for p in formatted_paths  # steps alternate entity/relation
        )

    return result


def community_detection(
    graph: nx.MultiDiGraph,
    max_communities: int = 10,
) -> List[Dict[str, Any]]:
    """
    Detect communities using Louvain algorithm on the undirected projection of the graph.

    Returns list of community dicts:
    [
      {
        "id": int,
        "size": int,
        "entities": [{"entity_text": str, "entity_type": str|None}],
        "central_entity": str | None   # highest-degree node in community
      }
    ]

    Returns [] if graph has no nodes or python-louvain is not installed.
    Limits to top max_communities by size.
    """
    if graph.number_of_nodes() == 0:
        return []

    try:
        import community as community_louvain
    except ImportError:
        return []

    # Louvain requires undirected graph
    undirected = graph.to_undirected()

    # Remove self-loops (can cause issues)
    undirected.remove_edges_from(nx.selfloop_edges(undirected))

    if undirected.number_of_edges() == 0:
        # No edges — each node is its own community
        communities: Dict[int, int] = {node: i for i, node in enumerate(undirected.nodes())}
    else:
        communities = community_louvain.best_partition(undirected)

    # Group nodes by community id
    community_groups: Dict[int, List[int]] = {}
    for node_id, comm_id in communities.items():
        community_groups.setdefault(comm_id, []).append(node_id)

    results = []
    for comm_id, node_ids in sorted(community_groups.items(), key=lambda x: -len(x[1])):
        entities = []
        for nid in node_ids:
            nd = graph.nodes.get(nid, {})
            entities.append({
                "entity_text": nd.get("entity_text", str(nid)),
                "entity_type": nd.get("entity_type"),
            })

        # Central entity = highest degree in the community subgraph
        central_entity = None
        if node_ids:
            sub = undirected.subgraph(node_ids)
            try:
                central_id = max(sub.degree(), key=lambda x: x[1])[0]
                central_entity = graph.nodes.get(central_id, {}).get("entity_text")
            except (ValueError, StopIteration):
                pass

        results.append({
            "id": comm_id,
            "size": len(node_ids),
            "entities": entities,
            "central_entity": central_entity,
        })

        if len(results) >= max_communities:
            break

    return results


# ---------------------------------------------------------------------------
# Phase 4: Full 6-step retrieval pipeline
# ---------------------------------------------------------------------------

def entity_retrieval(query: str, graph: nx.MultiDiGraph, top_k: int = 5) -> List[int]:
    """Find node IDs whose entity_text contains any word from the query."""
    query_words = [w.lower() for w in query.split() if len(w) > 2]
    matched = []
    for node_id, data in graph.nodes(data=True):
        entity_text = data.get("entity_text", "").lower()
        if any(word in entity_text for word in query_words):
            matched.append(node_id)
        if len(matched) >= top_k:
            break
    return matched


def neighborhood_expansion(
    entity_ids: List[int], graph: nx.MultiDiGraph, hops: int = 2
) -> Set[int]:
    """BFS from seed entities to collect neighboring nodes within `hops`."""
    visited: Set[int] = set(entity_ids)
    frontier: Set[int] = set(entity_ids)
    for _ in range(hops):
        next_frontier: Set[int] = set()
        for node_id in frontier:
            # outgoing neighbors
            for neighbor in graph.successors(node_id):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    visited.add(neighbor)
            # incoming neighbors
            for neighbor in graph.predecessors(node_id):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    visited.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    return visited


def graph_reranking(
    node_ids: Set[int],
    graph: nx.MultiDiGraph,
    query_vector: Optional[List[float]],
    top_k: int = 10,
) -> List[int]:
    """
    Score nodes by degree-based centrality proxy (or 0.5 fallback if no query_vector).
    Full vector-based reranking (cosine similarity against chunk vectors loaded from
    SQLite) would improve accuracy — add as a future enhancement.
    Returns top_k node IDs sorted by score descending.
    """
    scores = []

    for node_id in node_ids:
        score = 0.5  # default when no query_vector

        if query_vector is not None:
            # Use graph degree as proxy for node centrality / relevance
            degree = graph.degree(node_id)
            # Normalize: more connected → higher base score (capped at 0.7)
            score = 0.3 + min(0.4, degree * 0.05)

        scores.append((node_id, score))

    scores.sort(key=lambda x: -x[1])
    return [nid for nid, _ in scores[:top_k]]


async def context_assembly(
    top_node_ids: List[int],
    graph: nx.MultiDiGraph,
    db,  # sync Session
    char_budget: int = 3000,
) -> str:
    """
    Assemble context string from chunk texts stored in graph node metadata.
    Fetches chunk text from the Vector table via vector_external_id.
    Falls back gracefully if chunk text is not available.
    """
    from vectordb.models.db import Vector

    seen_chunks: set = set()
    context_parts = []
    total_chars = 0

    for node_id in top_node_ids:
        node_data = graph.nodes.get(node_id, {})
        chunk_id = node_data.get("chunk_id")
        vector_external_id = node_data.get("vector_external_id")

        # Avoid duplicate chunks
        dedup_key = vector_external_id or chunk_id
        if dedup_key and dedup_key in seen_chunks:
            continue
        if dedup_key:
            seen_chunks.add(dedup_key)

        # Try to get chunk text from Vector table
        chunk_text = None
        if vector_external_id:
            try:
                vec_row = db.query(Vector).filter_by(
                    external_id=vector_external_id
                ).first()
                if vec_row and vec_row.content:
                    chunk_text = vec_row.content
                elif vec_row and vec_row.meta and isinstance(vec_row.meta, dict):
                    chunk_text = vec_row.meta.get("text")
            except Exception:
                pass

        if chunk_text:
            remaining = char_budget - total_chars
            if remaining <= 0:
                break
            trimmed = chunk_text[:remaining]
            context_parts.append(trimmed)
            total_chars += len(trimmed)

    return "\n\n".join(context_parts) if context_parts else ""


async def graph_ask_pipeline(
    query: str,
    collection_id: int,
    graph: nx.MultiDiGraph,
    db,  # sync Session
    k: int = 5,
) -> Dict[str, Any]:
    """
    Full 6-step GraphRAG pipeline.

    Steps:
      1. entity_retrieval — NER: match query words against entity_text
      2. neighborhood_expansion — BFS 2 hops from matched entities
      3. path_analysis — relationship paths between top 2 entities (if 2+ found)
      4. graph_reranking — score/sort neighborhood nodes by degree proxy
      5. context_assembly — fetch chunk texts, deduplicate, trim to budget
      6. llm_answer — call generate_answer(query, context)

    Returns: {answer: str, sources: list, graph_context: dict}
    """
    from vectordb.services.embedding_service import embed_text_cached_async
    from vectordb.services.llm_service import generate_answer

    # Step 1: Entity retrieval
    entity_ids = entity_retrieval(query, graph, top_k=5)

    # Step 2: Neighborhood expansion
    if entity_ids:
        neighborhood = neighborhood_expansion(entity_ids, graph, hops=2)
    else:
        # fallback: use first 50 nodes when no entities matched
        neighborhood = set(list(graph.nodes())[:50])

    # Step 3: Path analysis (only if 2+ entities found)
    path_context = ""
    if len(entity_ids) >= 2:
        entity_texts = [
            graph.nodes.get(nid, {}).get("entity_text", "") for nid in entity_ids[:2]
        ]
        if entity_texts[0] and entity_texts[1]:
            path_result = path_analysis(graph, entity_texts[0], entity_texts[1], max_hops=3)
            if path_result["path_count"] > 0:
                path_steps = path_result["paths"][0]
                path_str = " → ".join(
                    s.get("entity", s.get("relation", "")) for s in path_steps
                )
                path_context = f"Relationship path: {path_str}"

    # Step 4: Graph reranking
    try:
        query_vector = await embed_text_cached_async(query)
    except Exception:
        query_vector = None
    top_node_ids = graph_reranking(neighborhood, graph, query_vector, top_k=k * 2)

    # Step 5: Context assembly
    context = await context_assembly(top_node_ids, graph, db)
    if path_context:
        context = path_context + "\n\n" + context

    # Step 6: LLM answer
    entities_used = [
        graph.nodes.get(nid, {}).get("entity_text", str(nid))
        for nid in entity_ids
    ]

    if not context.strip():
        return {
            "answer": "No relevant graph context found for this query.",
            "sources": [],
            "graph_context": {
                "entities_used": entities_used,
                "paths_used": [path_context] if path_context else [],
            },
        }

    try:
        # generate_answer returns a str (not a tuple)
        answer = await generate_answer(query, context)
        sources: List[Any] = []
    except Exception:
        answer = context[:500]  # graceful fallback
        sources = []

    return {
        "answer": answer,
        "sources": sources,
        "graph_context": {
            "entities_used": entities_used,
            "paths_used": [path_context] if path_context else [],
        },
    }


async def graph_hybrid_ask_pipeline(
    query: str,
    collection_name: str,
    collection_id: int,
    graph: nx.MultiDiGraph,
    db,
    backend,
    k: int = 5,
    vector_weight: float = 0.5,
    graph_hops: int = 2,
    include_graph_context: bool = True,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Hybrid GraphRAG: parallel vector search + graph traversal → RRF fusion → LLM answer."""
    from vectordb.services.embedding_service import embed_text_cached_async
    from vectordb.services.llm_service import generate_answer

    # Step 1: embed query once (used by both vector search and graph reranking)
    query_vector = await embed_text_cached_async(query)

    # Step 2: parallel retrieval
    async def _get_graph_nodes():
        seed_ids = entity_retrieval(query, graph, top_k=k)
        hood = neighborhood_expansion(seed_ids, graph, hops=graph_hops) if seed_ids else set()
        return seed_ids, hood

    vector_results, (seed_ids, neighborhood) = await asyncio.gather(
        backend.search(collection_name, query_vector, k=k * 2, offset=0, filters=None, user_id=user_id),
        _get_graph_nodes(),
    )

    # Step 3: build ranked lists
    vec_rank = {r["external_id"]: i + 1 for i, r in enumerate(vector_results)}

    top_graph_nodes = graph_reranking(neighborhood, graph, query_vector, top_k=k * 2)
    graph_eids_ranked = []
    for nid in top_graph_nodes:
        veid = graph.nodes.get(nid, {}).get("vector_external_id")
        if veid:
            graph_eids_ranked.append(veid)
    graph_rank = {eid: i + 1 for i, eid in enumerate(graph_eids_ranked)}

    # Step 4: RRF fusion
    RRF_K = 60
    all_eids = set(vec_rank) | set(graph_rank)
    fused = []
    for eid in all_eids:
        vr = vector_weight * (1.0 / (RRF_K + vec_rank[eid])) if eid in vec_rank else 0.0
        gr = (1 - vector_weight) * (1.0 / (RRF_K + graph_rank[eid])) if eid in graph_rank else 0.0
        in_v, in_g = eid in vec_rank, eid in graph_rank
        stype = "both" if (in_v and in_g) else ("vector" if in_v else "graph")
        fused.append({"external_id": eid, "score": vr + gr, "source_type": stype})
    fused.sort(key=lambda x: -x["score"])
    top_fused = fused[:k]

    # Step 5: batch fetch content (single SQL IN query)
    fused_eids = [f["external_id"] for f in top_fused]
    content_rows = []
    if fused_eids:
        content_rows = await backend.batch_get_vectors(
            collection_name, fused_eids, include_vectors=False, user_id=user_id
        )
    content_map = {r["external_id"]: r.get("content") or "" for r in content_rows}
    metadata_map = {r["external_id"]: r.get("metadata") for r in content_rows}
    for r in vector_results:
        if r["external_id"] not in metadata_map:
            metadata_map[r["external_id"]] = r.get("metadata")

    # Step 6: graph context enrichment
    entities_used = [
        graph.nodes.get(nid, {}).get("entity_text", "")
        for nid in seed_ids
        if graph.nodes.get(nid)
    ]
    relations_used = []
    if include_graph_context:
        for nid in seed_ids:
            for _src, tgt, _key, edata in graph.edges(nid, keys=True, data=True):
                tgt_text = graph.nodes.get(tgt, {}).get("entity_text", str(tgt))
                relations_used.append({
                    "source": graph.nodes.get(nid, {}).get("entity_text", str(nid)),
                    "relation": edata.get("relation_type", "related_to"),
                    "target": tgt_text,
                })

    # Step 7: context assembly (4000 char budget)
    CHAR_BUDGET = 4000
    parts, total = [], 0
    for item in top_fused:
        text = content_map.get(item["external_id"], "")
        if text and total < CHAR_BUDGET:
            chunk = text[:CHAR_BUDGET - total]
            parts.append(chunk)
            total += len(chunk)
    if include_graph_context and relations_used:
        rel_lines = [
            f'{r["source"]} --[{r["relation"]}]--> {r["target"]}'
            for r in relations_used[:20]
        ]
        graph_section = "Knowledge Graph Relationships:\n" + "\n".join(rel_lines)
        remaining = CHAR_BUDGET - total
        if remaining > 0:
            parts.append(graph_section[:remaining])
    context = "\n\n".join(parts)

    # Step 8: LLM answer with graph-aware context header
    graph_header = "Use the document context and knowledge graph relationships below to answer.\n\n"
    answer = await generate_answer(query, graph_header + context)

    # Step 9: build sources
    sources = [
        {
            "external_id": f["external_id"],
            "score": round(f["score"], 6),
            "content": content_map.get(f["external_id"]) or None,
            "metadata": metadata_map.get(f["external_id"]),
            "source_type": f["source_type"],
        }
        for f in top_fused
    ]

    return {
        "answer": answer,
        "sources": sources,
        "graph_context": {
            "entities_used": [e for e in entities_used if e],
            "relations_used": relations_used,
        },
        "retrieval_stats": {
            "vector_chunks": len(vec_rank),
            "graph_chunks": len(graph_rank),
            "fused_chunks": len(top_fused),
        },
    }
