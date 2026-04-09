---
title: Upload Document
sidebar_label: Upload Document
---

Upload a text document to be chunked and stored as vectors in a collection.

**`POST /v1/documents/upload`**

## Request

**Headers:**
```
x-api-key: your-api-key
Content-Type: multipart/form-data
```

**Body (multipart form data):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `collection_name` | string | Yes | Target collection name. The collection must already exist. |
| `file` | file | Yes | The document to upload. Currently only `.txt` files are supported. |
| `include_timing` | boolean | — | When `true`, the response includes a `timing_ms` object with `embedding_ms`, `storage_ms`, and `total_ms` breakdowns. Default: `false`. |

## Examples

### Basic upload

```bash
curl -X POST http://localhost:8000/v1/documents/upload \
  -H "x-api-key: your-key" \
  -F "collection_name=articles" \
  -F "file=@/path/to/document.txt"
```

### Upload with timing

```bash
curl -X POST http://localhost:8000/v1/documents/upload \
  -H "x-api-key: your-key" \
  -F "collection_name=articles" \
  -F "file=@/path/to/document.txt" \
  -F "include_timing=true"
```

## Response

```json
{
  "status": "success",
  "data": {
    "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "chunks_created": 12
  },
  "error": null
}
```

**With timing:**

```json
{
  "status": "success",
  "data": {
    "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "chunks_created": 12,
    "timing_ms": {
      "embedding_ms": 145.3,
      "storage_ms": 18.7,
      "total_ms": 164.0
    }
  },
  "error": null
}
```

:::note
The document is split into chunks, each chunk is embedded and stored as a vector in the specified collection. The `document_id` is a UUID assigned to the upload, and `chunks_created` indicates how many vector chunks were generated from the file.
:::

## Errors

| Code | Reason |
|------|--------|
| `404` | Collection not found |
| `401` | Missing or invalid API key |
| `403` | API key does not have write permission |
