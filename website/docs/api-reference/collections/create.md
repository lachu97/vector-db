---
id: create
title: Create Collection
sidebar_label: Create Collection
---

Create a new vector collection with a fixed dimension and distance metric.

**`POST /v1/collections`**

## Request

**Headers:**
```
x-api-key: your-api-key
Content-Type: application/json
```

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Unique collection name (letters, numbers, hyphens, underscores) |
| `dim` | integer | ✅ | Vector dimension. Must match your embedding model. |
| `distance_metric` | string | — | One of `cosine`, `l2`, or `ip`. Default: `cosine` |

## Example

```bash
curl -X POST http://localhost:8000/v1/collections \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "articles",
    "dim": 384,
    "distance_metric": "cosine"
  }'
```

## Response

```json
{
  "status": "success",
  "data": {
    "name": "articles",
    "dim": 384,
    "distance_metric": "cosine",
    "vector_count": 0,
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `409` | A collection with this name already exists |
| `422` | Invalid request body (missing required fields, invalid dim) |
| `401` | Missing or invalid API key |
| `403` | API key does not have write permission |
