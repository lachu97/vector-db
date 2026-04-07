---
id: get
title: Get Collection
sidebar_label: Get Collection
---

Get details for a single collection.

**`GET /v1/collections/{name}`**

## Request

**Headers:**
```
x-api-key: your-api-key
```

**Path Parameters:**

| Parameter | Description |
|-----------|-------------|
| `name` | Collection name |

## Example

```bash
curl http://localhost:8000/v1/collections/articles \
  -H "x-api-key: test-key"
```

## Response

```json
{
  "status": "success",
  "data": {
    "name": "articles",
    "dim": 384,
    "distance_metric": "cosine",
    "vector_count": 10482,
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection not found |
| `401` | Missing or invalid API key |
