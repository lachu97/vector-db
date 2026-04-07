---
id: keys
title: API Key Management
sidebar_label: API Keys
---

Manage API keys with role-based access control. Requires an `admin`-role key.

## Create API Key

**`POST /v1/admin/keys`**

```bash
curl -X POST http://localhost:8000/v1/admin/keys \
  -H "x-api-key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "production-app", "role": "readwrite"}'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Descriptive name for the key |
| `role` | string | ✅ | One of `admin`, `readwrite`, or `readonly` |

**Response:**

```json
{
  "status": "success",
  "data": {
    "id": 2,
    "name": "production-app",
    "key": "sk-rw-abc123def456...",
    "role": "readwrite",
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

:::warning
The `key` value is only returned once at creation time. Store it securely — it cannot be retrieved again.
:::

---

## List API Keys

**`GET /v1/admin/keys`**

```bash
curl http://localhost:8000/v1/admin/keys \
  -H "x-api-key: your-admin-key"
```

**Response:**

```json
{
  "status": "success",
  "data": {
    "keys": [
      {"id": 1, "name": "default", "role": "admin", "created_at": "..."},
      {"id": 2, "name": "production-app", "role": "readwrite", "created_at": "..."}
    ]
  }
}
```

Note: Key values are not returned in list responses.

---

## Delete API Key

**`DELETE /v1/admin/keys/{id}`**

```bash
curl -X DELETE http://localhost:8000/v1/admin/keys/2 \
  -H "x-api-key: your-admin-key"
```

**Response:**

```json
{
  "status": "success",
  "data": {
    "deleted": 2
  }
}
```
