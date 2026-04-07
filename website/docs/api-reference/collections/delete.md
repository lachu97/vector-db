---
id: delete
title: Delete Collection
sidebar_label: Delete Collection
---

Delete a collection and all its vectors permanently.

**`DELETE /v1/collections/{name}`**

## Request

**Headers:**
```
x-api-key: your-api-key
```

**Path Parameters:**

| Parameter | Description |
|-----------|-------------|
| `name` | Collection name |

## Example

```bash
curl -X DELETE http://localhost:8000/v1/collections/articles \
  -H "x-api-key: test-key"
```

## Response

```json
{
  "status": "success",
  "data": {
    "deleted": "articles"
  }
}
```

:::danger
This operation is irreversible. All vectors, metadata, and the HNSW index for this collection are permanently deleted.
:::

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection not found |
| `401` | Missing or invalid API key |
| `403` | API key does not have write permission |
