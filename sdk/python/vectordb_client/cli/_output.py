"""CLI output formatters (table and JSON modes)."""

from __future__ import annotations
import json
import sys
from typing import Any


def _json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def _row(*cells: str, widths: list[int]) -> str:
    return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths))


def _table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    print(_row(*headers, widths=widths))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(_row(*row, widths=widths))


def print_collections(items: list[dict], fmt: str) -> None:
    if fmt == "json":
        _json(items)
        return
    if not items:
        print("No collections found.")
        return
    rows = [
        [c["name"], str(c["dim"]), c["distance_metric"], str(c.get("vector_count", 0))]
        for c in items
    ]
    _table(["NAME", "DIM", "METRIC", "VECTORS"], rows)


def print_collection(c: dict, fmt: str) -> None:
    if fmt == "json":
        _json(c)
        return
    print(f"Name:    {c['name']}")
    print(f"Dim:     {c['dim']}")
    print(f"Metric:  {c['distance_metric']}")
    print(f"Vectors: {c.get('vector_count', 0)}")
    if c.get("created_at"):
        print(f"Created: {c['created_at']}")


def print_upsert(r: dict, fmt: str) -> None:
    if fmt == "json":
        _json(r)
        return
    status = r.get("status", "?")
    eid = r.get("external_id", "?")
    marker = "+" if status == "inserted" else "~"
    print(f"[{marker}] {eid}  ({status})")


def print_bulk_upsert(r: dict, fmt: str) -> None:
    if fmt == "json":
        _json(r)
        return
    results = r.get("results", [])
    inserted = sum(1 for x in results if x.get("status") == "inserted")
    updated = sum(1 for x in results if x.get("status") == "updated")
    print(f"Processed {len(results)} items: {inserted} inserted, {updated} updated.")


def print_search_results(results: list[dict], fmt: str) -> None:
    if fmt == "json":
        _json(results)
        return
    if not results:
        print("No results.")
        return
    rows = [
        [r["external_id"], f"{r.get('score', 0):.6f}", json.dumps(r.get("metadata") or {})]
        for r in results
    ]
    _table(["ID", "SCORE", "METADATA"], rows)


def print_delete(r: dict, fmt: str) -> None:
    if fmt == "json":
        _json(r)
        return
    print(f"Deleted: {r.get('external_id', r.get('name', '?'))}")


def print_batch_delete(r: dict, fmt: str) -> None:
    if fmt == "json":
        _json(r)
        return
    print(f"Deleted {r.get('deleted_count', 0)} vectors.")
    if r.get("not_found"):
        print(f"Not found: {', '.join(r['not_found'])}")


def print_health(h: dict, fmt: str) -> None:
    if fmt == "json":
        _json(h)
        return
    status = h.get("status", "?")
    mark = "OK" if status == "ok" else "WARN"
    print(f"Status:      {mark}")
    print(f"Uptime:      {h.get('uptime_seconds', '?')}s")
    print(f"Collections: {h.get('total_collections', 0)}")
    print(f"Vectors:     {h.get('total_vectors', 0)}")
    cols = h.get("collections", [])
    if cols:
        print()
        rows = [[c["name"], str(c["vector_count"]), str(c["dim"])] for c in cols]
        _table(["COLLECTION", "VECTORS", "DIM"], rows)


def print_similarity(score: float, fmt: str) -> None:
    if fmt == "json":
        _json({"score": score})
        return
    print(f"Similarity: {score:.6f}")


def err(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
