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
| `vector` | float[] | — | Array of floats. Length must match the collection's `dim`. Either `vector` or `text` must be provided. If both are given, `vector` takes precedence. |
| `text` | string | — | Plain text to embed. The backend generates a vector using the configured embedding model. Either `text` or `vector` must be provided. If both are given, `vector` takes precedence. |
| `metadata` | object | — | Arbitrary JSON metadata attached to the vector |
| `include_timing` | boolean | — | Default: `false`. When `true`, the response includes a `timing_ms` object with `embedding_ms`, `storage_ms`, and `total_ms` breakdowns. |

## Examples

**With vector:**

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

**With text and timing:**

```bash
curl -X POST http://localhost:8000/v1/collections/articles/upsert \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "doc-1",
    "text": "Getting started with vector databases",
    "metadata": {"title": "Getting started", "author": "Alice"},
    "include_timing": true
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

**With timing:**

```json
{
  "status": "success",
  "data": {
    "external_id": "doc-1",
    "status": "inserted",
    "timing_ms": {
      "embedding_ms": 12.4,
      "storage_ms": 3.1,
      "total_ms": 15.5
    }
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
