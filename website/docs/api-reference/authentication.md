---
id: authentication
title: Authentication
sidebar_label: Authentication
---

## Creating API Keys

API key management requires an `admin`-role key.

```bash
curl -X POST http://localhost:8000/v1/admin/keys \
  -H "x-api-key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "production-app", "role": "readwrite"}'
```

Response:

```json
{
  "status": "success",
  "data": {
    "id": 2,
    "name": "production-app",
    "key": "sk-rw-abc123...",
    "role": "readwrite",
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

:::warning
The API key value is only shown once at creation time. Store it securely.
:::

## Listing API Keys

```bash
curl http://localhost:8000/v1/admin/keys \
  -H "x-api-key: your-admin-key"
```

## Revoking an API Key

```bash
curl -X DELETE http://localhost:8000/v1/admin/keys/2 \
  -H "x-api-key: your-admin-key"
```

## Key Roles

| Role | Description |
|------|-------------|
| `admin` | Full access, including key management |
| `readwrite` | Create/delete collections, upsert/delete vectors, search |
| `readonly` | Search, list, and get operations only |

## Using API Keys

Pass the key in the `x-api-key` header on every request:

```bash
curl http://localhost:8000/v1/collections \
  -H "x-api-key: sk-rw-abc123..."
```

Or set it once in your SDK client:

```python
from vectordb_client import VectorDBClient

client = VectorDBClient(
    base_url="http://localhost:8000",
    api_key="sk-rw-abc123...",
)
```
