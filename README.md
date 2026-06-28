<div align="center">

# VectorDB

**Open-source vector database for AI applications.**  
Self-hosted. Sub-millisecond search. GraphRAG built-in. No cloud bill.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Dashboard](https://img.shields.io/badge/dashboard-vector--db--web-6366f1)](https://github.com/lachu97/vector-db-web)

[**Dashboard UI**](https://github.com/lachu97/vector-db-web) · [**API Docs**](https://vector-db-web.vercel.app/docs)· [**Benchmarks**](#performance)

</div>

---

## Why VectorDB?

| | Pinecone | Weaviate Cloud | **VectorDB** |
|---|---|---|---|
| Price | $70+/mo | $25+/mo | **Free** |
| Data leaves your infra | Yes | Yes | **Never** |
| p95 search latency | ~10ms | ~15ms | **< 0.6ms** |
| GraphRAG | No | No | **Yes** |
| Open source | No | Partial | **Yes** |
| Setup | Minutes | Minutes | **30 seconds** |

VectorDB is the **retrieval layer** for your LLM stack. Upload documents, store embeddings, run semantic search, and feed your LLM the right context — all from one self-hosted service.

---

## Quickstart

```bash
# No API key needed — embeddings run locally
docker run -p 8000:8000 lakshminarasimhan17/vector-db:latest
```

> Add `-e OPENAI_API_KEY=sk-...` only if you want `/v1/ask` (LLM answer generation) or GraphRAG. Core search, embeddings, and RAG retrieval work fully offline.

```bash
# Create a collection
curl -X POST http://localhost:8000/v1/collections \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "docs", "dim": 384, "distance_metric": "cosine"}'

# Upsert with text (auto-embedded — no client-side embedding needed)
curl -X POST http://localhost:8000/v1/collections/docs/upsert \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"external_id": "doc-1", "text": "Vector databases power fast semantic search"}'

# Search
curl -X POST http://localhost:8000/v1/collections/docs/search \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "nearest neighbor search", "k": 5}'
```

Interactive API explorer: **http://localhost:8000/docs**

---

## RAG in 3 calls

```bash
# 1. Upload a document (chunked + embedded automatically)
curl -X POST http://localhost:8000/v1/documents/upload \
  -H "x-api-key: test-key" \
  -F "collection_name=docs" \
  -F "file=@knowledge-base.txt"
# → {"document_id": "uuid", "chunks_created": 42}

# 2. Ask a question — retrieves context + generates an answer
curl -X POST http://localhost:8000/v1/ask \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the main benefits?", "collection": "docs", "k": 5}'
# → {"answer": "Based on the documents...", "sources": [...]}

# 3. Or retrieve raw chunks for your own LLM call
curl -X POST http://localhost:8000/v1/query \
  -H "x-api-key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "main benefits", "collection_name": "docs", "top_k": 5}'
# → {"results": [{"text": "...", "score": 0.92, "metadata": {...}}]}
```

---

## Features

### Core
- **HNSW indexing** — O(log n) approximate nearest-neighbor, sub-0.6ms at 5,000+ vectors
- **Auto-embedding** — pass `text` instead of a raw vector; the server embeds it using `all-MiniLM-L6-v2` (384-dim)
- **Metadata filtering** — exact-match filters on any metadata key, zero latency overhead
- **Hybrid search** — combine dense vector search with BM25 keyword search via `alpha` weighting
- **Cursor pagination** — scroll through millions of vectors with `POST /scroll`
- **Batch operations** — bulk upsert (1,000 vectors), batch delete, bulk search (20 queries)

### RAG
- **Document upload** — `.txt` files chunked + embedded automatically (`POST /v1/documents/upload`)
- **RAG query** — retrieve top-k text chunks with scores (`POST /v1/query`)
- **RAG ask** — retrieve + generate an LLM answer with source attribution (`POST /v1/ask`)

### GraphRAG (Pro/Scale)
- **Knowledge graph extraction** — entities and relations extracted from documents via LLM
- **Graph search** — traverse entity neighborhoods for context beyond direct vector matches
- **Path finding** — shortest path between two entities in the knowledge graph
- **Hybrid ask** — vector search + graph traversal fused via RRF, answer with per-source attribution
- **Flexible LLM provider** — OpenAI, Gemini, Anthropic, Ollama (any LiteLLM-compatible model)

### Infrastructure
- **Dual backend** — SQLite (zero-config, default) or PostgreSQL + pgvector (production scale)
- **Redis caching** — optional search result cache with configurable TTL
- **Multi-user auth** — register/login, per-user scoped collections and API keys
- **Role-based keys** — `admin` / `readwrite` / `readonly` with expiry support
- **Tier quotas** — free/starter/pro/scale with per-tier vector limits and RPM caps
- **Observability** — structured JSON logs (structlog), Prometheus metrics, OpenTelemetry tracing
- **Docker + Compose** — production-ready with Gunicorn + Uvicorn workers

---

## Performance

Benchmarked on 384-dim cosine-similarity vectors, p95 latency.

### PostgreSQL backend (pgvector HNSW)

| Operation | 100 vectors | 1,000 vectors | 5,000 vectors |
|-----------|:-----------:|:-------------:|:-------------:|
| **Vector search (top_k=10)** | 0.61ms | 0.55ms | **0.60ms** |
| **Filtered search** | 0.53ms | 0.56ms | **0.58ms** |
| **Recommendations** | 0.34ms | 0.33ms | **0.38ms** |
| **Bulk upsert (10 vectors)** | 2.11ms | 3.90ms | **2.07ms** |

### SQLite backend (HNSW, Phase 2 optimized)

| Operation | Before | After | Improvement |
|-----------|--------|-------|-------------|
| Filtered search (10k vecs) | 137ms | **14ms** | -90% |
| Filtered count (10k vecs) | 109ms | **15ms** | -86% |
| Batch delete (n=500) | 20ms | **11ms** | -44% |
| Sequential search (10k vecs) | 8.9ms | **5.7ms** | -36% |

**Latency is flat with scale.** HNSW indexing keeps search under 1ms from 100 to 5,000+ vectors.

---

## API Reference

All endpoints require `x-api-key: <key>` header. All responses follow:
```json
{"status": "success", "data": {...}, "error": null}
{"status": "error",   "data": null,  "error": {"code": 404, "message": "..."}}
```

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/auth/register` | Create account → returns user + admin API key |
| `POST` | `/v1/auth/login` | Sign in → returns user + API key |

### Collections
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/collections` | List all collections |
| `POST` | `/v1/collections` | Create — body: `{name, dim, distance_metric, description?}` |
| `GET` | `/v1/collections/:name` | Get one |
| `PATCH` | `/v1/collections/:name` | Update description |
| `GET` | `/v1/collections/:name/export` | Export all vectors (`?limit=N`) |
| `DELETE` | `/v1/collections/:name` | Delete |

### Vectors
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/collections/:name/upsert` | Single upsert — `{external_id, text\|vector, metadata?}` |
| `POST` | `/v1/collections/:name/bulk_upsert` | Batch upsert — `{vectors: [...]}` (max 1,000) |
| `POST` | `/v1/collections/:name/scroll` | Cursor-paginated browse — `{cursor?, limit?, filters?}` |
| `GET` | `/v1/collections/:name/vectors/:id` | Get single vector by ID |
| `POST` | `/v1/collections/:name/vectors/fetch` | Batch fetch by IDs (max 100) |
| `DELETE` | `/v1/collections/:name/delete/:id` | Delete one |
| `POST` | `/v1/collections/:name/delete_batch` | Batch delete — `{external_ids: [...]}` |

### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/collections/:name/search` | KNN search — `{text\|vector, k, filters?}` |
| `POST` | `/v1/collections/:name/hybrid_search` | Hybrid — `{text\|vector, query_text, k, alpha}` |
| `POST` | `/v1/collections/:name/recommend/:id` | Similar to a given ID — `{k}` |
| `POST` | `/v1/collections/:name/similarity` | Score between two vectors — `?id1=&id2=` |
| `POST` | `/v1/collections/:name/rerank` | Rerank candidates — `{text\|vector, candidates}` |
| `POST` | `/v1/collections/:name/bulk_search` | Up to 20 queries in one request |

### RAG
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/documents/upload` | Upload `.txt` → chunk + embed. Form: `collection_name`, `file` |
| `POST` | `/v1/query` | Semantic retrieval — `{query, collection_name, top_k?}` |
| `POST` | `/v1/ask` | Retrieval + LLM answer — `{query, collection, k?}` |

### GraphRAG (Pro/Scale)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/collections/:name/graph/status` | Entity + edge counts, build status |
| `POST` | `/v1/collections/:name/graph/search` | Graph entity search |
| `POST` | `/v1/collections/:name/graph/path` | Path between two entities |
| `POST` | `/v1/collections/:name/graph/ask` | Graph-only RAG answer (Scale) |
| `POST` | `/v1/collections/:name/graph/hybrid_ask` | Vector + graph fused answer (Pro/Scale) |
| `PATCH` | `/v1/collections/:name/graph/config` | Set extraction model + API keys |

### API Keys
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/admin/keys` | List keys |
| `POST` | `/v1/admin/keys` | Create — `{name, role, expires_in_days?}` |
| `PATCH` | `/v1/admin/keys/:id` | Update name/role/is_active |
| `POST` | `/v1/admin/keys/:id/rotate` | Regenerate key value |
| `DELETE` | `/v1/admin/keys/:id` | Hard delete |
| `GET` | `/v1/admin/keys/:id/usage` | Per-key usage stats |
| `GET` | `/v1/admin/keys/usage/summary` | Aggregate usage |

### Usage & Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/health` | Server status, uptime, vector/collection counts |
| `GET` | `/v1/usage` | Tier limits, current period usage, warnings |
| `GET` | `/v1/usage/history` | Monthly usage history |

---

## Configuration

All settings via environment variables (or `.env` file):

```env
# Auth
API_KEY=test-key                          # bootstrap admin key

# Storage
DATABASE_URL=sqlite:///./vectors.db       # or postgresql://user:pass@host/db
STORAGE_BACKEND=sqlite                    # sqlite | postgres

# Embeddings
EMBEDDING_MODEL=all-MiniLM-L6-v2          # 384-dim default
EMBEDDING_PROVIDER=sentence-transformers

# LLM (for /v1/ask)
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# Caching (optional)
REDIS_URL=redis://localhost:6379/0
CACHE_TTL=60

# Rate limiting
RATE_LIMIT_PER_MINUTE=100

# Workers
WORKERS=4
PORT=8000

# Observability
LOG_FORMAT=json                           # json | console
OTEL_ENABLED=false
OTEL_ENDPOINT=http://localhost:4318
```

---

## Getting Started

### Docker (recommended)

```bash
# SQLite (zero-config, no API key needed)
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  lakshminarasimhan17/vector-db:latest

# PostgreSQL
docker run -p 8000:8000 \
  -e STORAGE_BACKEND=postgres \
  -e DATABASE_URL=postgresql://user:pass@host/vectordb \
  lakshminarasimhan17/vector-db:latest

# With LLM answer generation (/v1/ask + GraphRAG)
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  lakshminarasimhan17/vector-db:latest
```

### Docker Compose

```bash
git clone https://github.com/lachu97/vector-db
cd vector-db
cp .env.example .env   # fill in your keys
docker compose up -d
```

### Local Development

```bash
git clone https://github.com/lachu97/vector-db
cd vector-db
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    FastAPI app                       │
│                                                      │
│  Auth → Rate limit → Quota check → Router            │
│                          │                           │
│         ┌────────────────┼────────────────┐          │
│         ▼                ▼                ▼          │
│    Collections        Vectors          RAG           │
│    (CRUD)          (upsert/search)  (upload/ask)     │
│                          │                ▼          │
│                          │         GraphRAG          │
│                          │      (extract/traverse)   │
│                          ▼                           │
│              ┌───────────────────────┐               │
│              │   VectorBackend       │               │
│              │  SQLite+HNSW (default)│               │
│              │  Postgres+pgvector    │               │
│              └───────────────────────┘               │
│                          │                           │
│              ┌───────────┴──────────┐               │
│              │   Redis cache        │               │
│              │   (optional)         │               │
│              └──────────────────────┘               │
└──────────────────────────────────────────────────────┘
```

**Pluggable backend** — swap SQLite for PostgreSQL+pgvector by setting one env var. Same API, same performance characteristics, different durability/scale profile.

---

## Tiers

| Tier | Vectors | Requests/mo | RPM | Price |
|------|---------|-------------|-----|-------|
| Free | 10,000 | 10,000 | 30 | $0 |
| Starter | 100,000 | 100,000 | 60 | $19/mo |
| Pro | 1,000,000 | 1,000,000 | 120 | $49/mo |
| Scale | 10,000,000 | 10,000,000 | 300 | $149/mo |

Bootstrap key (`test-key` / `API_KEY` env) bypasses all quota enforcement — full access for self-hosted users.

---

## Dashboard

Pair with the [VectorDB Admin Dashboard](https://github.com/lachu97/vector-db-web) — a React SPA with:

- Live health + metrics
- Collection and vector browser
- RAG upload + query UI
- GraphRAG knowledge explorer
- API key management
- Usage + tier charts

---

## Observability

```bash
# Prometheus metrics
curl http://localhost:8000/metrics

# Structured logs (JSON by default)
LOG_FORMAT=console uvicorn main:app  # human-readable in dev

# OpenTelemetry
OTEL_ENABLED=true OTEL_ENDPOINT=http://localhost:4318 uvicorn main:app
```

---

## Production Checklist

- [ ] Set `API_KEY` to a strong random value
- [ ] Switch to `STORAGE_BACKEND=postgres` for >100k vectors
- [ ] Set `OPENAI_API_KEY` for `/v1/ask` answer generation
- [ ] Mount a persistent volume for SQLite data (`-v $(pwd)/data:/app/data`)
- [ ] Put nginx in front for TLS + static file serving
- [ ] Enable Redis cache for high-traffic search workloads
- [ ] Set `OTEL_ENABLED=true` and point at your collector

---

## Contributing

PRs welcome. To run tests:

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## License

MIT — use it, fork it, self-host it.

---

<div align="center">
Built for developers who don't want another cloud bill.<br/>
<a href="https://github.com/lachu97/vector-db-web">Dashboard UI →</a>
</div>
