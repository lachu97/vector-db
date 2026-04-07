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
| `vector` | float[] | ✅ | Query vector to score candidates against |
| `candidates` | string[] | ✅ | List of external IDs to rerank |

## Example

```bash
curl -X POST http://localhost:8000/v1/collections/articles/rerank \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [0.1, 0.2, 0.3, 0.4],
    "candidates": ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]
  }'
```

## Response

```json
{
  "status": "success",
  "data": {
    "results": [
      {"external_id": "doc-3", "score": 0.9821, "metadata": {"title": "Most Relevant"}},
      {"external_id": "doc-1", "score": 0.9542, "metadata": {"title": "Second"}},
      {"external_id": "doc-5", "score": 0.8934, "metadata": {"title": "Third"}}
    ],
    "collection": "articles"
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
