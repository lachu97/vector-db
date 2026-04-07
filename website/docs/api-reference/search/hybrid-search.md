---
id: hybrid-search
title: Hybrid Search
sidebar_label: Hybrid Search
---

Combine vector similarity with keyword search using Reciprocal Rank Fusion (RRF).

**`POST /v1/collections/{name}/hybrid_search`**

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
| `vector` | float[] | ✅ | Query vector for semantic search |
| `query_text` | string | ✅ | Query text for keyword matching |
| `k` | integer | — | Number of results to return. Default: `10` |
| `alpha` | float | — | Blend factor: `1.0` = pure vector, `0.0` = pure keyword. Default: `0.5` |
| `filters` | object | — | Metadata filters |

## Example

```bash
curl -X POST http://localhost:8000/v1/collections/articles/hybrid_search \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [0.1, 0.2, 0.3, 0.4],
    "query_text": "machine learning transformers",
    "k": 10,
    "alpha": 0.7
  }'
```

## Response

```json
{
  "status": "success",
  "data": {
    "results": [
      {
        "external_id": "doc-12",
        "score": 0.8923,
        "metadata": {"title": "Attention Is All You Need"}
      }
    ],
    "collection": "articles",
    "k": 10,
    "alpha": 0.7
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `400` | Vector dimension mismatch |
| `404` | Collection not found |
| `401` | Missing or invalid API key |
