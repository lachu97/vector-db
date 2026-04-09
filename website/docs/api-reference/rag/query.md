---
title: RAG Query
sidebar_label: RAG Query
---

Query a collection using natural language. Returns the most relevant text chunks with similarity scores.

**`POST /v1/query`**

## Request

**Headers:**
```
x-api-key: your-api-key
Content-Type: application/json
```

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Natural language query text. The backend embeds this and performs a semantic search against the collection. |
| `collection_name` | string | Yes | Collection to search. |
| `top_k` | integer | — | Number of results to return. Default: `5`. |
| `filters` | object | — | Optional metadata filter. Only return chunks whose metadata contains the specified key-value pairs. |
| `include_timing` | boolean | — | When `true`, the response includes a `timing_ms` object with `embedding_ms`, `search_ms`, and `total_ms` breakdowns. Default: `false`. |

## Example

```bash
curl -X POST http://localhost:8000/v1/query \
  -H "x-api-key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does vector indexing work?",
    "collection_name": "articles",
    "top_k": 5,
    "filters": {"source": "docs"}
  }'
```

## Response

```json
{
  "status": "success",
  "data": {
    "query": "How does vector indexing work?",
    "collection": "articles",
    "results": [
      {
        "text": "Vector indexing uses approximate nearest neighbor algorithms like HNSW to enable fast similarity search over high-dimensional embeddings...",
        "score": 0.9342,
        "metadata": {"source": "docs", "page": 3},
        "external_id": "a1b2c3d4-chunk-0"
      },
      {
        "text": "HNSW builds a hierarchical graph structure where each layer provides increasingly refined proximity information...",
        "score": 0.8917,
        "metadata": {"source": "docs", "page": 5},
        "external_id": "a1b2c3d4-chunk-4"
      }
    ]
  },
  "error": null
}
```

**With timing:**

```json
{
  "status": "success",
  "data": {
    "query": "How does vector indexing work?",
    "collection": "articles",
    "results": [
      {
        "text": "Vector indexing uses approximate nearest neighbor algorithms...",
        "score": 0.9342,
        "metadata": {"source": "docs", "page": 3},
        "external_id": "a1b2c3d4-chunk-0"
      }
    ],
    "timing_ms": {
      "embedding_ms": 11.8,
      "search_ms": 3.2,
      "total_ms": 15.0
    }
  },
  "error": null
}
```

:::note
Unlike the `/v1/collections/{name}/search` endpoint which requires a raw vector, the RAG query endpoint accepts plain text. The backend handles embedding the query internally before performing the search.
:::

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection not found |
| `401` | Missing or invalid API key |
