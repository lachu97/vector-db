---
title: Export Vectors
sidebar_label: Export
---

Export all vectors in a collection as float arrays with metadata.

**`GET /v1/collections/{collection_name}/export`**

## Request

**Headers:**
```
x-api-key: your-api-key
```

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `collection_name` | string | Yes | Collection to export from. |

**Query Parameters:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | integer | `10000` | Maximum number of vectors to export. Must be between 1 and 100,000. |

## Example

```bash
curl http://localhost:8000/v1/collections/articles/export?limit=100 \
  -H "x-api-key: your-key"
```

## Response

```json
{
  "status": "success",
  "data": {
    "collection": "articles",
    "dim": 384,
    "distance_metric": "cosine",
    "count": 2,
    "vectors": [
      {
        "external_id": "doc-1",
        "vector": [0.123, 0.456, "..."],
        "metadata": {"title": "Hello World"}
      },
      {
        "external_id": "doc-2",
        "vector": [0.789, 0.012, "..."],
        "metadata": {"title": "Getting Started"}
      }
    ]
  },
  "error": null
}
```

:::note
For large collections, use the `limit` parameter to paginate exports. Vectors are returned in database insertion order.
:::

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection not found |
| `401` | Missing or invalid API key |
