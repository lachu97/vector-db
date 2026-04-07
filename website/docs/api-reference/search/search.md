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
| `vector` | float[] | ✅ | Query vector. Length must match collection dimension. |
| `k` | integer | — | Number of results to return. Default: `10` |
| `offset` | integer | — | Pagination offset. Default: `0` |
| `filters` | object | — | Metadata key-value filters. Only returns vectors matching all filters. |

## Example

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

## Response

```json
{
  "status": "success",
  "data": {
    "results": [
      {
        "external_id": "doc-1",
        "score": 0.9823,
        "metadata": {"title": "Hello World", "author": "Alice"}
      },
      {
        "external_id": "doc-5",
        "score": 0.9541,
        "metadata": {"title": "Another Article", "author": "Alice"}
      }
    ],
    "collection": "articles",
    "k": 5
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `400` | Vector dimension doesn't match collection dimension |
| `404` | Collection not found |
| `401` | Missing or invalid API key |
