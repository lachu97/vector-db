---
id: similarity
title: Similarity
sidebar_label: Similarity
---

Compute the cosine similarity between two stored vectors.

**`POST /v1/collections/{name}/similarity`**

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

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id1` | string | ✅ | External ID of the first vector |
| `id2` | string | ✅ | External ID of the second vector |

## Example

```bash
curl -X POST "http://localhost:8000/v1/collections/articles/similarity?id1=doc-1&id2=doc-2" \
  -H "x-api-key: test-key"
```

## Response

```json
{
  "status": "success",
  "data": {
    "id1": "doc-1",
    "id2": "doc-2",
    "similarity": 0.9234
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection or one of the vectors not found |
| `401` | Missing or invalid API key |
