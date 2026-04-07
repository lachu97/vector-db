"""
vdb — VectorDB command-line interface.

Global options (set via flags or environment variables):
  --url      / VECTORDB_URL      Base URL of the server (default: http://localhost:8000)
  --api-key  / VECTORDB_API_KEY  API key for authentication
  --output   / VECTORDB_OUTPUT   Output format: table (default) or json

Usage examples:
  vdb health
  vdb collections list
  vdb collections create my-col --dim 384
  vdb collections delete my-col
  vdb vectors upsert my-col doc-1 '[0.1, 0.2, 0.3]' --metadata '{"title": "hello"}'
  vdb vectors delete my-col doc-1
  vdb search my-col '[0.1, 0.2, 0.3]' --k 5
  vdb recommend my-col doc-1 --k 5
  vdb hybrid-search my-col "search query" '[0.1, 0.2]' --alpha 0.7
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import click

from vectordb_client.client import VectorDBClient
from vectordb_client.exceptions import VectorDBError
from vectordb_client.cli._output import (
    err,
    print_collection,
    print_collections,
    print_delete,
    print_batch_delete,
    print_upsert,
    print_bulk_upsert,
    print_search_results,
    print_health,
    print_similarity,
)

# ---------------------------------------------------------------------------
# Shared context object
# ---------------------------------------------------------------------------

class _Ctx:
    def __init__(self, url: str, api_key: str, output: str) -> None:
        self.url = url
        self.api_key = api_key
        self.output = output

    def client(self) -> VectorDBClient:
        return VectorDBClient(base_url=self.url, api_key=self.api_key)


pass_ctx = click.make_pass_decorator(_Ctx)


# ---------------------------------------------------------------------------
# Vector parsing helper
# ---------------------------------------------------------------------------

def _parse_vector(value: str) -> list[float]:
    """Parse a JSON array string or @filename into a float list."""
    if value.startswith("@"):
        path = value[1:]
        try:
            with open(path) as f:
                value = f.read()
        except OSError as e:
            raise click.BadParameter(f"Cannot read file '{path}': {e}")
    try:
        vec = json.loads(value)
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"Invalid JSON: {e}")
    if not isinstance(vec, list):
        raise click.BadParameter("Vector must be a JSON array, e.g. '[0.1, 0.2, 0.3]'")
    try:
        return [float(x) for x in vec]
    except (TypeError, ValueError) as e:
        raise click.BadParameter(f"Vector elements must be numbers: {e}")


def _parse_metadata(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        meta = json.loads(value)
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"--metadata must be valid JSON: {e}")
    if not isinstance(meta, dict):
        raise click.BadParameter("--metadata must be a JSON object, e.g. '{\"key\": \"value\"}'")
    return meta


# ---------------------------------------------------------------------------
# Root command group
# ---------------------------------------------------------------------------

@click.group()
@click.option(
    "--url",
    envvar="VECTORDB_URL",
    default="http://localhost:8000",
    show_default=True,
    help="VectorDB server URL.",
)
@click.option(
    "--api-key",
    envvar="VECTORDB_API_KEY",
    required=True,
    help="API key (or set VECTORDB_API_KEY).",
)
@click.option(
    "--output",
    "-o",
    envvar="VECTORDB_OUTPUT",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.version_option(version="0.1.0", prog_name="vdb")
@click.pass_context
def cli(ctx: click.Context, url: str, api_key: str, output: str) -> None:
    """VectorDB command-line interface."""
    ctx.obj = _Ctx(url=url, api_key=api_key, output=output)
    ctx.ensure_object(_Ctx)


# ---------------------------------------------------------------------------
# health / ping
# ---------------------------------------------------------------------------

@cli.command()
@pass_ctx
def health(ctx: _Ctx) -> None:
    """Show server health and collection statistics."""
    try:
        c = ctx.client()
        h = c.observability.health()
        import dataclasses
        d = {
            "status": h.status,
            "uptime_seconds": h.uptime_seconds,
            "total_collections": h.total_collections,
            "total_vectors": h.total_vectors,
            "collections": h.collections,
        }
        print_health(d, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


@cli.command()
@pass_ctx
def ping(ctx: _Ctx) -> None:
    """Check if the server is reachable."""
    c = ctx.client()
    if c.ping():
        print(f"OK  {ctx.url}")
    else:
        err(f"Cannot reach {ctx.url}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# collections
# ---------------------------------------------------------------------------

@cli.group()
def collections() -> None:
    """Manage collections."""


@collections.command("list")
@pass_ctx
def collections_list(ctx: _Ctx) -> None:
    """List all collections."""
    try:
        c = ctx.client()
        cols = c.collections.list()
        items = [
            {
                "name": col.name,
                "dim": col.dim,
                "distance_metric": col.distance_metric,
                "vector_count": col.vector_count,
            }
            for col in cols
        ]
        print_collections(items, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


@collections.command("create")
@click.argument("name")
@click.option("--dim", "-d", required=True, type=int, help="Vector dimensionality.")
@click.option(
    "--metric", "-m",
    type=click.Choice(["cosine", "l2", "ip"], case_sensitive=False),
    default="cosine",
    show_default=True,
    help="Distance metric.",
)
@pass_ctx
def collections_create(ctx: _Ctx, name: str, dim: int, metric: str) -> None:
    """Create a new collection."""
    try:
        c = ctx.client()
        col = c.collections.create(name, dim=dim, distance_metric=metric)
        d = {
            "name": col.name,
            "dim": col.dim,
            "distance_metric": col.distance_metric,
            "vector_count": col.vector_count,
        }
        print_collection(d, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


@collections.command("get")
@click.argument("name")
@pass_ctx
def collections_get(ctx: _Ctx, name: str) -> None:
    """Get details for a collection."""
    try:
        c = ctx.client()
        col = c.collections.get(name)
        d = {
            "name": col.name,
            "dim": col.dim,
            "distance_metric": col.distance_metric,
            "vector_count": col.vector_count,
            "created_at": col.created_at,
        }
        print_collection(d, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


@collections.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@pass_ctx
def collections_delete(ctx: _Ctx, name: str, yes: bool) -> None:
    """Delete a collection and all its vectors."""
    if not yes:
        click.confirm(
            f"Delete collection '{name}' and ALL its vectors? This cannot be undone.",
            abort=True,
        )
    try:
        c = ctx.client()
        r = c.collections.delete(name)
        if ctx.output == "json":
            import json as _json
            print(_json.dumps(r))
        else:
            print(f"Deleted collection '{name}'.")
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


# ---------------------------------------------------------------------------
# vectors
# ---------------------------------------------------------------------------

@cli.group()
def vectors() -> None:
    """Upsert and delete vectors."""


@vectors.command("upsert")
@click.argument("collection")
@click.argument("id")
@click.argument("vector")
@click.option("--metadata", "-m", default=None, help="JSON metadata object.")
@click.option("--namespace", "-n", default=None, help="Optional namespace.")
@pass_ctx
def vectors_upsert(
    ctx: _Ctx,
    collection: str,
    id: str,
    vector: str,
    metadata: str | None,
    namespace: str | None,
) -> None:
    """Upsert a vector into COLLECTION with the given ID.

    VECTOR is a JSON array, e.g. '[0.1, 0.2, 0.3]', or '@file.json'.
    """
    vec = _parse_vector(vector)
    meta = _parse_metadata(metadata)
    try:
        c = ctx.client()
        r = c.vectors.upsert(collection, id, vec, meta, namespace)
        print_upsert({"external_id": r.external_id, "status": r.status}, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


@vectors.command("delete")
@click.argument("collection")
@click.argument("id")
@pass_ctx
def vectors_delete(ctx: _Ctx, collection: str, id: str) -> None:
    """Delete a single vector by ID."""
    try:
        c = ctx.client()
        r = c.vectors.delete(collection, id)
        print_delete({"external_id": id, **r}, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


@vectors.command("delete-batch")
@click.argument("collection")
@click.argument("ids", nargs=-1, required=True)
@pass_ctx
def vectors_delete_batch(ctx: _Ctx, collection: str, ids: tuple[str, ...]) -> None:
    """Delete multiple vectors by ID.

    Example: vdb vectors delete-batch my-col id1 id2 id3
    """
    try:
        c = ctx.client()
        r = c.vectors.delete_batch(collection, list(ids))
        d = {
            "deleted_count": r.get("deleted_count", 0),
            "not_found": r.get("not_found", []),
        }
        print_batch_delete(d, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("collection")
@click.argument("vector")
@click.option("--k", default=10, show_default=True, type=int, help="Number of results.")
@click.option("--offset", default=0, show_default=True, type=int, help="Pagination offset.")
@click.option(
    "--filter", "filters",
    multiple=True,
    metavar="KEY=VALUE",
    help="Metadata filter (repeatable). E.g. --filter tag=foo",
)
@pass_ctx
def search(
    ctx: _Ctx,
    collection: str,
    vector: str,
    k: int,
    offset: int,
    filters: tuple[str, ...],
) -> None:
    """KNN vector search in COLLECTION.

    VECTOR is a JSON array, e.g. '[0.1, 0.2, 0.3]', or '@file.json'.
    """
    vec = _parse_vector(vector)
    parsed_filters: dict[str, Any] | None = None
    if filters:
        parsed_filters = {}
        for f in filters:
            if "=" not in f:
                raise click.BadParameter(f"Filter must be KEY=VALUE, got: '{f}'", param_hint="--filter")
            key, val = f.split("=", 1)
            parsed_filters[key.strip()] = val.strip()
    try:
        c = ctx.client()
        result = c.search.search(collection, vec, k=k, offset=offset, filters=parsed_filters)
        rows = [
            {"external_id": r.external_id, "score": r.score, "metadata": r.metadata}
            for r in result.results
        ]
        print_search_results(rows, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


@cli.command()
@click.argument("collection")
@click.argument("id")
@click.option("--k", default=10, show_default=True, type=int, help="Number of results.")
@pass_ctx
def recommend(ctx: _Ctx, collection: str, id: str, k: int) -> None:
    """Find similar vectors to ID in COLLECTION (excludes the source vector)."""
    try:
        c = ctx.client()
        result = c.search.recommend(collection, id, k=k)
        rows = [
            {"external_id": r.external_id, "score": r.score, "metadata": r.metadata}
            for r in result.results
        ]
        print_search_results(rows, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


@cli.command()
@click.argument("collection")
@click.argument("id1")
@click.argument("id2")
@pass_ctx
def similarity(ctx: _Ctx, collection: str, id1: str, id2: str) -> None:
    """Compute cosine similarity between two stored vectors."""
    try:
        c = ctx.client()
        score = c.search.similarity(collection, id1, id2)
        print_similarity(score, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)


@cli.command("hybrid-search")
@click.argument("collection")
@click.argument("query_text")
@click.argument("vector")
@click.option("--k", default=10, show_default=True, type=int, help="Number of results.")
@click.option(
    "--alpha",
    default=0.5,
    show_default=True,
    type=float,
    help="Vector weight (0.0=text only, 1.0=vector only).",
)
@pass_ctx
def hybrid_search(
    ctx: _Ctx,
    collection: str,
    query_text: str,
    vector: str,
    k: int,
    alpha: float,
) -> None:
    """Hybrid vector + text search using Reciprocal Rank Fusion.

    VECTOR is a JSON array, e.g. '[0.1, 0.2, 0.3]', or '@file.json'.
    """
    if not 0.0 <= alpha <= 1.0:
        raise click.BadParameter("alpha must be between 0.0 and 1.0", param_hint="--alpha")
    vec = _parse_vector(vector)
    try:
        c = ctx.client()
        result = c.search.hybrid_search(collection, query_text, vec, k=k, alpha=alpha)
        rows = [
            {"external_id": r.external_id, "score": r.score, "metadata": r.metadata}
            for r in result.results
        ]
        print_search_results(rows, ctx.output)
    except VectorDBError as e:
        err(str(e))
        sys.exit(1)
