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
| `query_text` | string | ✅ | Text query for keyword matching. |
| `vector` | float[] | — | Query vector for semantic similarity. Now optional -- if omitted, the backend auto-embeds `query_text` to generate the vector. |
| `k` | integer | — | Number of results to return. Default: `10` |
| `offset` | integer | — | Pagination offset. Default: `0` |
| `alpha` | float | — | Blend factor: `1.0` = pure vector, `0.0` = pure keyword. Default: `0.5` |
| `filters` | object | — | Metadata filters |
| `include_timing` | boolean | — | Default: `false`. When `true`, the response includes a `timing_ms` object with `embedding_ms`, `search_ms`, and `total_ms` breakdowns. |

## Examples

**With vector:**

```bash
curl -X POST http://localhost:8000/v1/collections/articles/hybrid_search \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "machine learning transformers",
    "vector": [0.1, 0.2, 0.3],
    "k": 10,
    "alpha": 0.7
  }'
```

**Text only (auto-embed) with timing:**

```bash
curl -X POST http://localhost:8000/v1/collections/articles/hybrid_search \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "machine learning transformers",
    "k": 10,
    "alpha": 0.7,
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
        "external_id": "doc-88",
        "score": 0.9731,
        "metadata": {"title": "Transformers explained"}
      },
      {
        "external_id": "doc-12",
        "score": 0.9412,
        "metadata": {"title": "Intro to machine learning"}
      }
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
      {
        "external_id": "doc-88",
        "score": 0.9731,
        "metadata": {"title": "Transformers explained"}
      }
    ],
    "timing_ms": {
      "embedding_ms": 12.1,
      "search_ms": 5.3,
      "total_ms": 17.4
    }
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `400` | Vector dimension mismatch |
| `404` | Collection not found |
| `401` | Missing or invalid API key |
