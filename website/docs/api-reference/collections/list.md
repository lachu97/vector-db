---
id: list
title: List Collections
sidebar_label: List Collections
---

List all collections.

**`GET /v1/collections`**

## Request

**Headers:**
```
x-api-key: your-api-key
```

## Example

```bash
curl http://localhost:8000/v1/collections \
  -H "x-api-key: test-key"
```

## Response

```json
{
  "status": "success",
  "data": {
    "collections": [
      {
        "name": "articles",
        "dim": 384,
        "distance_metric": "cosine",
        "vector_count": 10482,
        "created_at": "2024-01-15T10:00:00Z"
      },
      {
        "name": "product-images",
        "dim": 512,
        "distance_metric": "l2",
        "vector_count": 55291,
        "created_at": "2024-01-16T09:00:00Z"
      }
    ]
  }
}
```
