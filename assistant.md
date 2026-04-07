# VectorDB Assistant

VectorDB is a lightweight, self-hosted vector database with a REST API for storing, searching, and managing vector embeddings.

## Key facts

- All API requests require an `x-api-key` header
- Default API key for local development is `test-key`
- All responses use the envelope format: `{ "status": "success"|"error", "data": ..., "error": ... }`
- HTTP status is always 200 — check the `status` field in the body for errors

## Core concepts

- **Collections** — namespaces for vectors; each has a fixed `dim` and `distance_metric` (`cosine`, `l2`, or `ip`)
- **Vectors** — float arrays stored with an `external_id` and optional JSON metadata
- **Upsert** — insert or update; same `external_id` in the same collection = update
- **Hybrid search** — combines vector similarity and keyword matching via Reciprocal Rank Fusion (RRF); `alpha=1.0` is pure vector, `alpha=0.0` is pure keyword

## Running locally

```bash
docker compose up --build
# or
pip install -r requirements.txt && uvicorn main:app --reload
```

Server starts on `http://localhost:8000`. Swagger UI at `/docs`.

## SDKs

- Python: `pip install vectordb-client` → `VectorDBClient` (sync) and `AsyncVectorDBClient`
- TypeScript: `npm install vectordb-client` → `VectorDBClient`
- CLI: `pip install vectordb-client` → `vdb` command
