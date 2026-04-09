---
title: Update Collection
sidebar_label: Update
---

Update a collection's description.

**`PATCH /v1/collections/{collection_name}`**

## Request

**Headers:**
```
x-api-key: your-api-key
Content-Type: application/json
```

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `collection_name` | string | Yes | Name of the collection to update. |

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string \| null | — | New description for the collection. Pass `null` to clear the description. |

## Example

```bash
curl -X PATCH http://localhost:8000/v1/collections/articles \
  -H "x-api-key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated description for articles"}'
```

## Response

```json
{
  "status": "success",
  "data": {
    "name": "articles",
    "dim": 384,
    "distance_metric": "cosine",
    "description": "Updated description for articles",
    "vector_count": 150,
    "created_at": "2024-01-15T10:00:00Z"
  },
  "error": null
}
```

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection not found |
| `401` | Missing or invalid API key |
