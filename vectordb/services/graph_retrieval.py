"""
Graph retrieval pipeline — modular functions for /graph/ask and graph endpoints.

Phase 2: path_analysis — shortest paths between entity pairs
Phase 3: community_detection — Louvain community detection (added later)
Phase 4: full pipeline (added later)
"""
import networkx as nx
from typing import List, Dict, Optional, Any


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
