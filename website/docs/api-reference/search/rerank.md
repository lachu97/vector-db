---
id: rerank
title: Rerank
sidebar_label: Rerank
---

Re-score a set of candidate vectors against a query vector. Useful for two-stage retrieval: fetch a broad candidate set, then rerank by relevance.

**`POST /v1/collections/{name}/rerank`**

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
| `vector` | float[] | — | Query vector to score candidates against. Either `vector` or `text` must be provided. If both are given, `vector` takes precedence. |
| `text` | string | — | Plain text query. The backend generates a vector using the configured embedding model. Either `text` or `vector` must be provided. If both are given, `vector` takes precedence. |
| `candidates` | string[] | ✅ | List of external IDs to rerank |
| `include_timing` | boolean | — | Default: `false`. When `true`, the response includes a `timing_ms` object with `embedding_ms`, `search_ms`, and `total_ms` breakdowns. |

## Examples

**With vector:**

```bash
curl -X POST http://localhost:8000/v1/collections/articles/rerank \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [0.1, 0.2, 0.3, 0.4],
    "candidates": ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]
  }'
```

**With text and timing:**

```bash
curl -X POST http://localhost:8000/v1/collections/articles/rerank \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "machine learning best practices",
    "candidates": ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"],
    "include_timing": true
  }'
```

## Response

```json
{
  "status": "success",
  "data": {
    "results": [
      {"external_id": "doc-3", "score": 0.9812, "metadata": {}},
      {"external_id": "doc-1", "score": 0.9541, "metadata": {}},
      {"external_id": "doc-5", "score": 0.9201, "metadata": {}}
    ]
  }
}
```

**With timing:**

```json
{
  "status": "success",
  "data": {
    "results": [
      {"external_id": "doc-3", "score": 0.9812, "metadata": {}},
      {"external_id": "doc-1", "score": 0.9541, "metadata": {}}
    ],
    "timing_ms": {
      "embedding_ms": 10.5,
      "search_ms": 4.1,
      "total_ms": 14.6
    }
  }
}
```

Results are returned sorted by score (highest first).

## Errors

| Code | Reason |
|------|--------|
| `400` | Vector dimension mismatch |
| `404` | Collection not found |
| `401` | Missing or invalid API key |
