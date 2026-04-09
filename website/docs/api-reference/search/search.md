---
id: search
title: Vector Search
sidebar_label: Search
---

Find the K nearest vectors to a query vector, with optional metadata filtering and pagination.

**`POST /v1/collections/{name}/search`**

## Request

**Headers:**
```
x-api-key: your-api-key
Content-Type: application/json
```

**Path Parameters:**

| Parameter | Description |
|-----------|-------------|
| `name` | Collection name |

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `vector` | float[] | — | Query vector. Length must match collection dimension. Either `vector` or `text` must be provided. If both are given, `vector` takes precedence. |
| `text` | string | — | Plain text query. The backend generates a vector using the configured embedding model. Either `text` or `vector` must be provided. If both are given, `vector` takes precedence. |
| `k` | integer | — | Number of results to return. Default: `10` |
| `offset` | integer | — | Pagination offset. Default: `0` |
| `filters` | object | — | Metadata key-value filters. Only returns vectors matching all filters. |
| `include_timing` | boolean | — | Default: `false`. When `true`, the response includes a `timing_ms` object with `embedding_ms`, `search_ms`, and `total_ms` breakdowns. |

## Examples

**With vector:**

```bash
curl -X POST http://localhost:8000/v1/collections/articles/search \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [0.1, 0.2, 0.3, 0.4],
    "k": 5,
    "filters": {"author": "Alice"}
  }'
```

**With text and timing:**

```bash
curl -X POST http://localhost:8000/v1/collections/articles/search \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "getting started with machine learning",
    "k": 5,
    "filters": {"author": "Alice"},
    "include_timing": true
  }'
```

## Response

```json
{
  "status": "success",
  "data": {
    "results": [
      {
        "external_id": "doc-42",
        "score": 0.9823,
        "metadata": {"title": "Getting started", "author": "Alice"}
      },
      {
        "external_id": "doc-17",
        "score": 0.9541,
        "metadata": {"title": "Advanced topics", "author": "Alice"}
      }
    ],
    "total_count": 150,
    "k": 5,
    "offset": 0
  }
}
```

**With timing:**

```json
{
  "status": "success",
  "data": {
    "results": [
      {
        "external_id": "doc-42",
        "score": 0.9823,
        "metadata": {"title": "Getting started", "author": "Alice"}
      }
    ],
    "total_count": 150,
    "k": 5,
    "offset": 0,
    "timing_ms": {
      "embedding_ms": 11.2,
      "search_ms": 2.8,
      "total_ms": 14.0
    }
  }
}
```

`total_count` returns the total number of vectors in the collection (before filtering). Use it with `offset` and `k` for pagination. Returns `-1` if the backend does not support counting.

## Errors

| Code | Reason |
|------|--------|
| `400` | Vector dimension doesn't match collection dimension |
| `404` | Collection not found |
| `401` | Missing or invalid API key |
