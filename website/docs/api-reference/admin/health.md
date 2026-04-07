---
id: health
title: Health Check
sidebar_label: Health Check
---

Get server health status, uptime, and collection statistics.

**`GET /v1/health`**

## Request

**Headers:**
```
x-api-key: your-api-key
```

## Example

```bash
curl http://localhost:8000/v1/health \
  -H "x-api-key: test-key"
```

## Response

```json
{
  "status": "success",
  "data": {
    "status": "ok",
    "total_vectors": 65773,
    "total_collections": 3,
    "uptime_seconds": 3600.5,
    "collections": [
      {"name": "articles", "vector_count": 10482},
      {"name": "product-images", "vector_count": 55291}
    ]
  }
}
```

## Prometheus Metrics

For Prometheus scraping, the `/metrics` endpoint is available without authentication:

```bash
curl http://localhost:8000/metrics
```

Returns Prometheus text format metrics including:
- `vectordb_requests_total` — total requests by endpoint and status
- `vectordb_request_duration_seconds` — request latency histogram
- `vectordb_vectors_total` — total vectors per collection
- `vectordb_collections_total` — total number of collections
