---
id: collections
title: Collections
sidebar_label: Collections
---

## What is a Collection?

A collection is a named group of vectors that share:
- A fixed **dimension** (number of floats per vector)
- A **distance metric** used for all searches

Every vector operation — upsert, search, delete — targets a specific collection.

```
┌─────────────────────────────────────┐
│ Collection: "product-embeddings"    │
│ Dimension: 384                      │
│ Metric: cosine                      │
├─────────────────────────────────────┤
│ doc-1 → [0.12, 0.34, ..., 0.89]    │
│ doc-2 → [0.55, 0.11, ..., 0.23]    │
│ doc-3 → [0.88, 0.67, ..., 0.01]    │
└─────────────────────────────────────┘
```

## Creating a Collection

```python
from vectordb_client import VectorDBClient

client = VectorDBClient(base_url="http://localhost:8000", api_key="your-key")

col = client.collections.create(
    name="product-embeddings",
    dim=384,
    distance_metric="cosine",
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | ✅ | Unique collection name. Letters, numbers, hyphens, underscores. |
| `dim` | integer | ✅ | Vector dimension. Must match your embedding model. |
| `distance_metric` | string | — | One of `cosine`, `l2`, or `ip`. Default: `cosine`. |

## Choosing a Dimension

Your dimension must match whatever embedding model produces the vectors.

| Model | Dimension |
|-------|-----------|
| `all-MiniLM-L6-v2` (sentence-transformers) | 384 |
| `text-embedding-ada-002` (OpenAI) | 1536 |
| `text-embedding-3-small` (OpenAI) | 1536 |
| `text-embedding-3-large` (OpenAI) | 3072 |
| `BERT-base` | 768 |
| `nomic-embed-text` (Ollama) | 768 |

:::warning
The dimension is fixed at creation time and cannot be changed. If you need a different dimension, create a new collection and re-index.
:::

## Multiple Collections

Use separate collections to isolate different data types or models.

```python
# Separate collections for different content types
client.collections.create("article-embeddings", dim=384, distance_metric="cosine")
client.collections.create("product-embeddings", dim=1536, distance_metric="cosine")
client.collections.create("user-profiles", dim=768, distance_metric="ip")
```

## Listing and Getting Collections

```python
# List all
collections = client.collections.list()
for col in collections:
    print(col.name, col.dim, col.vector_count)

# Get one
col = client.collections.get("product-embeddings")
print(col.vector_count)
```

## Deleting a Collection

Deleting a collection removes all its vectors permanently.

```python
client.collections.delete("old-collection")
```

:::danger
Collection deletion is irreversible. All vectors and metadata in the collection are permanently removed.
:::
