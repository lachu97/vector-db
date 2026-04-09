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
| `items` | object[] | ✅ | Array of vector objects (see below). Max: 1000 items. |
| `include_timing` | boolean | — | Default: `false`. When `true`, the response includes a `timing_ms` object with `embedding_ms`, `storage_ms`, and `total_ms` breakdowns. |

Each item object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `external_id` | string | ✅ | Unique identifier |
| `vector` | float[] | — | Array of floats matching collection dimension. Either `vector` or `text` must be provided per item. If both are given, `vector` takes precedence. |
| `text` | string | — | Plain text to embed. The backend generates the vector. Either `text` or `vector` must be provided. If both are given, `vector` takes precedence. |
| `metadata` | object | — | Arbitrary JSON metadata |

## Examples

**With vectors:**

```bash
curl -X POST http://localhost:8000/v1/collections/articles/bulk_upsert \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"external_id": "doc-1", "vector": [0.1, 0.2, 0.3], "metadata": {"title": "A"}},
      {"external_id": "doc-2", "vector": [0.4, 0.5, 0.6], "metadata": {"title": "B"}},
      {"external_id": "doc-3", "vector": [0.7, 0.8, 0.9]}
    ]
  }'
```

**With text and timing:**

```bash
curl -X POST http://localhost:8000/v1/collections/articles/bulk_upsert \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "external_id": "doc-1",
        "text": "Introduction to vector databases",
        "metadata": {"title": "First article"}
      },
      {
        "external_id": "doc-2",
        "text": "Advanced similarity search techniques",
        "metadata": {"title": "Second article"}
      }
    ],
    "include_timing": true
  }'
```

## Response

```json
{
  "status": "success",
  "data": {
    "results": [
      {"external_id": "doc-1", "status": "inserted"},
      {"external_id": "doc-2", "status": "inserted"}
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
      {"external_id": "doc-1", "status": "inserted"},
      {"external_id": "doc-2", "status": "inserted"}
    ],
    "timing_ms": {
      "embedding_ms": 24.8,
      "storage_ms": 5.2,
      "total_ms": 30.0
    }
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
