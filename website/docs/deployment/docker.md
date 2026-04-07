---
id: docker
title: Docker Deployment
sidebar_label: Docker
---

## Docker Compose (recommended)

The easiest way to run VectorDB in production.

```bash
git clone https://github.com/lachu97/vector-db
cd vector-db
docker compose up --build -d
```

The server starts on port `8000`. Verify it's running:

```bash
curl http://localhost:8000/v1/health -H "x-api-key: your-key"
```

## Configuration

Edit `docker-compose.yml` to configure the server:

```yaml
services:
  vectordb:
    build: .
    ports:
      - "8000:8000"
    environment:
      API_KEY: your-secret-key          # Change this!
      WORKERS: 4                         # Gunicorn worker processes
      PORT: 8000
      VECTOR_DIM: 384                    # Default dim for legacy endpoints
      MAX_ELEMENTS: 10000                # Max vectors per HNSW index
      LOG_FORMAT: json                   # json (prod) or console (dev)
    volumes:
      - ./data:/app/data                 # Persist indexes
      - ./vectors.db:/app/vectors.db     # Persist database
```

:::warning
Always change `API_KEY` before deploying to any network-accessible environment.
:::

## With Redis Cache

Add a Redis service for high-throughput search caching:

```yaml
services:
  vectordb:
    build: .
    ports:
      - "8000:8000"
    environment:
      API_KEY: your-secret-key
      REDIS_URL: redis://redis:6379
      CACHE_TTL: 60
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

## With PostgreSQL + pgvector

For production-scale deployments, swap SQLite for PostgreSQL:

```yaml
services:
  vectordb:
    build: .
    ports:
      - "8000:8000"
    environment:
      API_KEY: your-secret-key
      STORAGE_BACKEND: postgres
      DB_URL: postgresql+asyncpg://vectordb:password@postgres:5432/vectordb
    depends_on:
      - postgres

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: vectordb
      POSTGRES_USER: vectordb
      POSTGRES_PASSWORD: password
    volumes:
      - pg_data:/var/lib/postgresql/data

volumes:
  pg_data:
```

## Persistence

By default, VectorDB stores data in:
- `vectors.db` — SQLite database (collections, vectors, metadata)
- `data/` — HNSW index files (one per collection)

Mount both as Docker volumes to persist data across restarts:

```yaml
volumes:
  - ./data:/app/data
  - ./vectors.db:/app/vectors.db
```

## Health Check

```bash
# Check server status
curl http://localhost:8000/v1/health \
  -H "x-api-key: your-key"

# Prometheus metrics
curl http://localhost:8000/metrics
```

## Stopping and Restarting

```bash
# Stop (graceful — flushes HNSW indexes to disk)
docker compose down

# Restart
docker compose up -d

# View logs
docker compose logs -f vectordb
```
