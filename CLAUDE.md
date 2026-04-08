# Vector DB — Project Context

## Overview
A lightweight, self-hosted vector database providing REST APIs for storing, searching, and managing vector embeddings with metadata. Built with FastAPI + HNSWlib + SQLite. Targeting startups and small-scale apps that need semantic search without expensive managed services.

## Tech Stack
- **Framework:** FastAPI + Uvicorn + Gunicorn
- **Vector Index:** HNSWlib (HNSW approximate nearest neighbor), per-collection indexes
- **Database:** SQLite via SQLAlchemy (vectors stored as binary BLOB, metadata as JSON)
- **Migrations:** Alembic (schema versioning)
- **Validation:** Pydantic + pydantic-settings
- **Containerization:** Docker + Docker Compose
- **Testing:** pytest + httpx (236 tests, 4 skipped for PostgreSQL without live DB)
- **Python SDK:** `sdk/python/vectordb_client` — sync (`VectorDBClient`) and async (`AsyncVectorDBClient`) clients

## Project Structure
```
vector-db-mvp/
├── vectordb/                  # Main Python package
│   ├── __init__.py
│   ├── app.py                 # FastAPI app factory with lifespan events
│   ├── config.py              # Pydantic Settings (centralized config)
│   ├── auth.py                # API key verification
│   ├── models/
│   │   ├── __init__.py
│   │   ├── db.py              # SQLAlchemy models (Collection, Vector) + WAL mode
│   │   └── schemas.py         # Pydantic request/response schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── collections.py     # Collection CRUD (create, list, get, delete)
│   │   ├── vectors.py         # upsert, bulk_upsert, delete, batch_delete
│   │   ├── search.py          # search, recommend, similarity, rerank, hybrid_search
│   │   └── admin.py           # health, root
│   ├── services/
│   │   ├── __init__.py
│   │   └── vector_service.py  # encode/decode vectors, normalize, helpers
│   └── indexing/
│       ├── __init__.py
│       ├── hnsw.py            # HNSWIndexer (thread-safe wrapper)
│       └── manager.py         # IndexManager (per-collection index management)
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Shared fixtures (test DB, client, indexer)
│   ├── test_admin.py          # Health, root tests
│   ├── test_vectors.py        # Upsert, bulk_upsert, delete tests (legacy)
│   ├── test_search.py         # Search, recommend, similarity tests (legacy)
│   ├── test_collections.py    # Collection CRUD + scoped ops tests
│   ├── test_batch_delete.py   # Batch deletion tests
│   ├── test_rerank.py         # Rerank endpoint tests
│   └── test_hybrid_search.py  # Hybrid search tests
├── migrations/                # Alembic migrations
│   ├── env.py                 # Alembic env (auto-reads DB_URL from config)
│   └── versions/              # Migration scripts
├── data/                      # Runtime data (per-collection index files)
├── main.py                    # Entrypoint (imports from vectordb.app)
├── alembic.ini                # Alembic configuration
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Dev/test dependencies
├── pyproject.toml             # Project metadata
├── Dockerfile
├── docker-compose.yml
├── .env
├── .gitignore
└── CLAUDE.md                  # This file
```

## API Endpoints (v2)
All endpoints (except `/`) require `x-api-key` header.

### Collection Management
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/v1/collections` | Create a collection (name, dim, distance_metric) |
| GET | `/v1/collections` | List all collections |
| GET | `/v1/collections/{name}` | Get collection details |
| DELETE | `/v1/collections/{name}` | Delete collection + all its vectors |

### Collection-Scoped Operations
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/v1/collections/{name}/upsert` | Insert/update vector |
| POST | `/v1/collections/{name}/bulk_upsert` | Batch insert/update |
| POST | `/v1/collections/{name}/search` | KNN search with filters + pagination |
| POST | `/v1/collections/{name}/recommend/{id}` | Similar vectors (excludes self) |
| POST | `/v1/collections/{name}/similarity` | Cosine similarity between two vectors |
| POST | `/v1/collections/{name}/rerank` | Re-score candidates against query vector |
| POST | `/v1/collections/{name}/hybrid_search` | Combined vector + text search (RRF) |
| DELETE | `/v1/collections/{name}/delete/{id}` | Delete single vector |
| POST | `/v1/collections/{name}/delete_batch` | Batch delete vectors |

### Legacy Endpoints (route to "default" collection)
| Method | Endpoint |
|--------|----------|
| POST | `/v1/upsert`, `/v1/bulk_upsert`, `/v1/search`, `/v1/recommend/{id}` |
| POST | `/v1/similarity`, `/v1/rerank`, `/v1/hybrid_search` |
| DELETE | `/v1/delete/{id}` |
| GET | `/v1/health`, `/` |

## Key Design Decisions
- **Collections:** Each collection has its own HNSW index, dimension, and distance metric
- **IndexManager:** Manages per-collection HNSW indexes, lazy-loaded on first access
- **Distance metrics:** cosine, l2, ip — configured per collection at creation time
- **Legacy compatibility:** Old `/v1/*` endpoints auto-create a "default" collection
- Vectors are L2-normalized at upsert time for cosine similarity
- Vectors stored as binary BLOB (`np.float32.tobytes()`) — ~8x smaller than JSON
- Per-collection HNSW indexes persisted to `data/{collection_name}.bin` on shutdown
- SQLite WAL mode enabled for concurrent read/write performance
- Filtered search uses HNSW over-fetch + post-filter (10x oversample), with DB fallback
- bulk_upsert uses batched DB commit + batched index insertion
- Hybrid search uses word-level text matching + vector search merged via Reciprocal Rank Fusion (RRF)
- Rerank computes cosine similarity between query and each candidate vector
- Schema changes managed via Alembic migrations (`render_as_batch=True` for SQLite)
- Unique constraint on (collection_id, external_id) — same external_id allowed across collections

## Development Rules
- **Every new feature or code change must have accompanying test cases.** No code is considered complete without tests that cover its functionality. Tests must pass before marking work as done.
- **SDK sync rule:** Any new API endpoint, new request/response field, or changed behavior MUST be reflected in both SDKs before the work is considered done:
  - Python SDK: `sdk/python/vectordb_client/` — update `_resources.py`, `_async_resources.py`, `models.py`, and bump version in `pyproject.toml` + `__init__.py`
  - TypeScript SDK: `sdk/typescript/src/` — update `types.ts`, the relevant resource file under `resources/`, and bump version in `package.json`
  - Add tests for new SDK methods in `tests/test_phase6_python_sdk.py` and `sdk/typescript/src/__tests__/`
- **Frontend sync rule:** Any new API endpoint or changed behavior MUST be documented in `vector-db-web/CLAUDE.md` (Backend Changelog section) so the frontend Claude can implement it. Include: endpoint path, method, request body, response shape, and required UI changes.

## Running
```bash
# Local
pip install -r requirements.txt
uvicorn main:app --reload

# Docker
docker compose up --build
```

## Testing
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Migrations
```bash
# Generate a new migration after model changes
alembic revision --autogenerate -m "description of change"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| API_KEY | test-key | API authentication key |
| VECTOR_DIM | 384 | Default vector dimensionality (for legacy endpoints) |
| INDEX_PATH | data/index.bin | Base directory for index files |
| MAX_ELEMENTS | 10000 | Max HNSW index capacity per collection |
| EF_CONSTRUCTION | 200 | HNSW build-time parameter |
| M | 16 | HNSW graph connectivity |
| EF_QUERY | 50 | HNSW query-time parameter |
| DB_URL | sqlite:///./vectors.db | Database connection string |
| PORT | 8000 | Server port |
| WORKERS | 4 | Gunicorn worker count |

---

## Roadmap

### Completed
- [x] **Phase 0: Foundation Cleanup** — Project restructure, config management, bug fixes, testing infra
- [x] **Phase 1: Performance & Storage** — Binary BLOB vectors, HNSW over-fetch filtered search, batched bulk_upsert, WAL mode, Alembic migrations
- [x] **Phase 2: Core Features** — Collections/namespaces, multiple distance metrics, pagination, batch delete, rerank, hybrid search, 57 tests

### Phase 3: Security & Auth (Completed)
- [x] Multi-API key system with roles (admin, readwrite, readonly)
- [x] Rate limiting (per API key, sliding window, in-memory)
- [x] CORS configuration
- [x] Request validation hardening (max dimensions, metadata size, batch size)

### Phase 4: Observability (Completed)
- [x] Structured logging (structlog) — JSON in prod, console in dev, all loggers migrated
- [x] Metrics endpoint (vector count, latency, throughput) — vectordb_requests_total, vectordb_request_duration_seconds, vectordb_vectors_total, vectordb_collections_total
- [x] Prometheus integration — GET /metrics (no auth, text/plain Prometheus format)
- [x] OpenTelemetry tracing — auto-instruments FastAPI + SQLAlchemy, disabled by default (OTEL_ENABLED=false)

### Phase 5: Scale & Storage Backends (Completed)
- [x] Pluggable storage backend architecture — VectorBackend ABC with domain exceptions; routers are now thin async wrappers
- [x] Async SQLAlchemy + async endpoints — all endpoints are async def; SQLite via aiosqlite, PostgreSQL via asyncpg
- [x] PostgreSQL + pgvector backend — per-collection dynamic tables with Vector(dim) type + HNSW index; selected via STORAGE_BACKEND=postgres
- [x] Redis caching layer — CachingBackend decorator wraps any backend; no-op when REDIS_URL is empty; cache invalidated on writes

### Phase 6: Developer Experience
- [x] Python SDK (`sdk/python/vectordb_client`) — sync + async clients, full API coverage, 38 tests
- [x] TypeScript SDK (`sdk/typescript/src`) — `VectorDBClient` with full API coverage, 49 Jest tests
- [x] CLI tool (`sdk/python/vectordb_client/cli/`) — `vdb` command, 46 tests
- [ ] Admin dashboard UI (React/Next.js)
- [x] Documentation site (`docs/`) — Mintlify, 30 pages, full API reference + OpenAPI spec

### Phase 7: Cloud & Managed Service
- [ ] Managed hosting (free/pro/scale tiers)
- [ ] Kubernetes deployment
- [ ] Tenant isolation
- [ ] Backup & disaster recovery
