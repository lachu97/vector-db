---
id: bulk-upsert
title: Bulk Upsert Vectors
sidebar_label: Bulk Upsert
---

Insert or update multiple vectors in a single request. More efficient than individual upserts for large ingestion jobs.

**`POST /v1/collections/{name}/bulk_upsert`**

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
| `vectors` | object[] | ✅ | Array of vector objects (see below) |

Each vector object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `external_id` | string | ✅ | Unique identifier |
| `vector` | float[] | ✅ | Array of floats matching collection dimension |
| `metadata` | object | — | Arbitrary JSON metadata |

## Example

```bash
curl -X POST http://localhost:8000/v1/collections/articles/bulk_upsert \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": [
      {"external_id": "doc-1", "vector": [0.1, 0.2, 0.3], "metadata": {"title": "A"}},
      {"external_id": "doc-2", "vector": [0.4, 0.5, 0.6], "metadata": {"title": "B"}},
      {"external_id": "doc-3", "vector": [0.7, 0.8, 0.9]}
    ]
  }'
```

## Response

```json
{
  "status": "success",
  "data": {
    "results": [
      {"external_id": "doc-1", "status": "inserted"},
      {"external_id": "doc-2", "status": "inserted"},
      {"external_id": "doc-3", "status": "inserted"}
    ]
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `400` | Vector dimension mismatch or batch exceeds `MAX_BATCH_SIZE` |
| `404` | Collection not found |
| `401` | Missing or invalid API key |
| `403` | API key does not have write permission |
