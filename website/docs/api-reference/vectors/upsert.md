---
id: upsert
title: Upsert Vector
sidebar_label: Upsert Vector
---

Insert or update a single vector. If a vector with the same `external_id` already exists in the collection, it is updated.

**`POST /v1/collections/{name}/upsert`**

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
| `external_id` | string | ✅ | Unique identifier for this vector within the collection |
| `vector` | float[] | ✅ | Array of floats. Length must match the collection's `dim`. |
| `metadata` | object | — | Arbitrary JSON metadata attached to the vector |

## Example

```bash
curl -X POST http://localhost:8000/v1/collections/articles/upsert \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "doc-1",
    "vector": [0.1, 0.2, 0.3, 0.4],
    "metadata": {"title": "Hello World", "author": "Alice"}
  }'
```

## Response

```json
{
  "status": "success",
  "data": {
    "external_id": "doc-1",
    "status": "inserted"
  }
}
```

The `status` field is `"inserted"` for new vectors and `"updated"` for existing ones.

## Errors

| Code | Reason |
|------|--------|
| `400` | Vector dimension doesn't match collection dimension |
| `404` | Collection not found |
| `401` | Missing or invalid API key |
| `403` | API key does not have write permission |
