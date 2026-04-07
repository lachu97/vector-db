---
id: recommend
title: Recommendations
sidebar_label: Recommend
---

Find vectors similar to a stored vector. The source vector is excluded from results.

**`POST /v1/collections/{name}/recommend/{id}`**

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
| `id` | External ID of the source vector |

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `k` | integer | — | Number of recommendations to return. Default: `10` |
| `filters` | object | — | Metadata filters |

## Example

```bash
curl -X POST http://localhost:8000/v1/collections/articles/recommend/doc-1 \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"k": 5}'
```

## Response

```json
{
  "status": "success",
  "data": {
    "results": [
      {
        "external_id": "doc-7",
        "score": 0.9521,
        "metadata": {"title": "Related Article"}
      }
    ],
    "collection": "articles",
    "source_id": "doc-1",
    "k": 5
  }
}
```

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection or source vector not found |
| `401` | Missing or invalid API key |
