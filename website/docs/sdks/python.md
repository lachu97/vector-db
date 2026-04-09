---
id: python
title: Python SDK
sidebar_label: Python SDK
---

## Installation

```bash
pip install vdb-python
```

Or install from source:

```bash
pip install git+https://github.com/lachu97/vector-db.git#subdirectory=sdk/python
```

## Initializing the Client

```python
from vectordb_client import VectorDBClient

client = VectorDBClient(
    base_url="http://localhost:8000",
    api_key="your-api-key",
)
```

Use as a context manager to ensure the connection is closed:

```python
with VectorDBClient(base_url="http://localhost:8000", api_key="your-key") as client:
    results = client.search.search("my-col", vector, k=5)
```

## Async Client

For async applications (FastAPI, asyncio):

```python
from vectordb_client import AsyncVectorDBClient

async with AsyncVectorDBClient(base_url="http://localhost:8000", api_key="your-key") as client:
    col = await client.collections.create("my-col", dim=384)
    results = await client.search.search("my-col", vector, k=5)
```

---

## Auth (Registration & Login)

```python
# Register a new user (no api_key needed for this call)
result = client.auth.register("user@example.com", "securepassword")
api_key = result["api_key"]["key"]  # Use this key for subsequent calls

# Login
result = client.auth.login("user@example.com", "securepassword")
api_key = result["api_key"]["key"]
```

---

## Collections

```python
# Create (with optional description)
col = client.collections.create("articles", dim=384, distance_metric="cosine", description="Blog article embeddings")

# List
cols = client.collections.list()

# Get
col = client.collections.get("articles")
print(col.name, col.dim, col.vector_count, col.description)

# Update description
col = client.collections.update("articles", "Updated description")

# Clear description
col = client.collections.update("articles", None)

# Export all vectors
export = client.collections.export("articles", limit=5000)
print(export.count)  # number of vectors exported
for v in export.vectors:
    print(v.external_id, len(v.vector), v.metadata)

# Delete
client.collections.delete("articles")
```

## Vectors

```python
# Upsert with a raw vector
result = client.vectors.upsert(
    collection="articles",
    external_id="doc-1",
    vector=[0.1, 0.2, ..., 0.9],
    metadata={"title": "Hello", "tags": ["ml", "nlp"]},
)
print(result.status)  # "inserted" or "updated"

# Upsert with raw text — the server embeds it for you
result = client.vectors.upsert(
    collection="articles",
    external_id="doc-2",
    text="An intro to vector databases",
    metadata={"title": "Intro"},
)

# Opt into timing metrics (embedding_ms, storage_ms, total_ms)
result = client.vectors.upsert(
    collection="articles",
    external_id="doc-3",
    text="Another article",
    include_timing=True,
)
print(result.timing_ms.embedding_ms, result.timing_ms.total_ms)

# Bulk upsert — mix vectors and text in the same batch
items = [
    {"external_id": "doc-a", "vector": vectors[0], "metadata": {"i": 0}},
    {"external_id": "doc-b", "text": "Second article body"},
]
bulk = client.vectors.bulk_upsert("articles", items, include_timing=True)
print(len(bulk.inserted), len(bulk.updated))
print(bulk.timing_ms.embedding_ms, bulk.timing_ms.storage_ms)

# Delete
client.vectors.delete("articles", "doc-1")

# Batch delete
client.vectors.delete_batch("articles", ["doc-1", "doc-2", "doc-3"])
```

## Search

```python
# KNN search with a raw vector (returns total_count for pagination)
results = client.search.search(
    collection="articles",
    vector=query_vector,
    k=10,
    offset=0,
    filters={"tags": "ml"},  # optional metadata filter
)
print(f"Showing {len(results)} of {results.total_count} total vectors")
for r in results:
    print(r.external_id, r.score, r.metadata)

# Search with plain text — the server embeds the query for you (cached)
results = client.search.search(
    collection="articles",
    text="machine learning tutorials",
    k=10,
)

# Opt into timing metrics (embedding_ms, search_ms, total_ms)
results = client.search.search(
    collection="articles",
    text="deep learning",
    k=10,
    include_timing=True,
)
print(results.timing_ms.embedding_ms, results.timing_ms.search_ms)

# Recommendations (similar to a stored vector)
recs = client.search.recommend("articles", external_id="doc-1", k=5)

# Cosine similarity between two stored vectors
score = client.search.similarity("articles", id1="doc-1", id2="doc-2")

# Rerank a candidate set with a vector...
reranked = client.search.rerank(
    collection="articles",
    query_vector=query_vector,
    candidates=["doc-1", "doc-2", "doc-3"],
)

# ...or rerank with text
reranked = client.search.rerank(
    collection="articles",
    text="machine learning best practices",
    candidates=["doc-1", "doc-2", "doc-3"],
    include_timing=True,
)
print(reranked.timing_ms.embedding_ms)

# Hybrid search — vector is now optional; backend auto-embeds query_text if omitted
results = client.search.hybrid_search(
    collection="articles",
    query_text="machine learning",
    k=10,
    alpha=0.7,
    include_timing=True,
)
```

## API Keys

Manage API keys programmatically (requires admin role):

```python
# Create a key with optional expiry
key = client.keys.create("production-app", role="readwrite", expires_in_days=90)
print(key.key)  # only shown once — save it!

# List all keys
keys = client.keys.list()
for k in keys:
    print(k.id, k.name, k.role, k.is_active)

# Get a single key
key = client.keys.get(key_id=2)

# Update name/role
client.keys.update(key_id=2, name="renamed-key", role="readonly")

# Revoke / Restore
client.keys.revoke(key_id=2)
client.keys.restore(key_id=2)

# Rotate (regenerate key value)
rotated = client.keys.rotate(key_id=2)
print(rotated.key)  # new key value — shown once

# Usage stats for a key
usage = client.keys.get_usage(key_id=2)
print(usage.total_requests, usage.last_24h, usage.by_endpoint)

# Usage summary across all keys
summary = client.keys.get_usage_summary()
print(summary["overall"]["total_requests"])

# Delete
client.keys.delete(key_id=2)
```

## RAG (Document Upload & Query)

```python
# Upload a text document to a collection
result = client.documents.upload(
    collection_name="articles",
    file_path="/path/to/document.txt",
)
print(result.document_id)    # UUID of the uploaded document
print(result.chunks_created) # number of chunks generated

# Upload with timing metrics (embedding_ms, storage_ms, total_ms)
result = client.documents.upload(
    collection_name="articles",
    file_path="/path/to/document.txt",
    include_timing=True,
)
print(result.timing_ms.total_ms)

# Query a collection with natural language
results = client.query.query(
    query="How does vector indexing work?",
    collection_name="articles",
    top_k=5,
    filters={"source": "docs"},
    include_timing=True,
)
print(results.timing_ms.embedding_ms, results.timing_ms.search_ms)
for r in results:
    print(r.text, r.score, r.metadata, r.external_id)
```

## Error Handling

```python
from vectordb_client.exceptions import (
    NotFoundError,
    AlreadyExistsError,
    DimensionMismatchError,
    AuthenticationError,
    RateLimitError,
    VectorDBError,
)

try:
    client.collections.create("my-col", dim=384)
except AlreadyExistsError:
    print("Collection already exists")
except DimensionMismatchError as e:
    print(f"Wrong dimension: {e}")
except AuthenticationError:
    print("Invalid API key")
except VectorDBError as e:
    print(f"Unexpected error: {e} (status={e.status_code})")
```

## Health Check

```python
health = client.observability.health()
print(health.status)            # "ok"
print(health.total_vectors)     # total across all collections
print(health.total_collections)
print(health.uptime_seconds)
```
