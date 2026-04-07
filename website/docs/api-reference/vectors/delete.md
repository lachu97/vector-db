---
id: delete
title: Delete Vector
sidebar_label: Delete Vector
---

Delete a single vector by its external ID.

**`DELETE /v1/collections/{name}/delete/{id}`**

## Request

**Headers:**
```
x-api-key: your-api-key
```

**Path Parameters:**

| Parameter | Description |
|-----------|-------------|
| `name` | Collection name |
| `id` | External ID of the vector to delete |

## Example

```bash
curl -X DELETE http://localhost:8000/v1/collections/articles/delete/doc-1 \
  -H "x-api-key: test-key"
```

## Response

```json
{
  "status": "success",
  "data": {
    "deleted": "doc-1"
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection or vector not found |
| `401` | Missing or invalid API key |
| `403` | API key does not have write permission |
