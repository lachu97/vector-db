---
id: delete-batch
title: Batch Delete Vectors
sidebar_label: Batch Delete
---

Delete multiple vectors by their external IDs in a single request.

**`POST /v1/collections/{name}/delete_batch`**

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
| `external_ids` | string[] | ✅ | List of external IDs to delete |

## Example

```bash
curl -X POST http://localhost:8000/v1/collections/articles/delete_batch \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"external_ids": ["doc-1", "doc-2", "doc-3"]}'
```

## Response

```json
{
  "status": "success",
  "data": {
    "deleted_count": 3,
    "deleted_ids": ["doc-1", "doc-2", "doc-3"]
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection not found |
| `401` | Missing or invalid API key |
| `403` | API key does not have write permission |
