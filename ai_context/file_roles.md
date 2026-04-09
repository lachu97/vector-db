# File Roles

## App Core

| File | Role |
|------|------|
| `vectordb/app.py` | FastAPI factory, lifespan (init_db, backend.startup, initialize_provider), middleware, router registration |
| `vectordb/config.py` | Pydantic Settings — all env vars, defaults, .env loading |
| `vectordb/auth.py` | API key lookup, role hierarchy (readonly/readwrite/admin), `require_readonly`/`require_readwrite`/`require_admin` dependencies, `ApiKeyInfo(key, name, role, user_id)` |

## Routers (HTTP layer only)

| File | Endpoints |
|------|-----------|
| `vectordb/routers/auth.py` | `POST /v1/auth/register`, `POST /v1/auth/login` (no auth required) |
| `vectordb/routers/collections.py` | CRUD `/v1/collections` (user_id scoped) |
| `vectordb/routers/vectors.py` | upsert, bulk_upsert, delete, batch_delete — accepts vector OR text |
| `vectordb/routers/search.py` | search, recommend, similarity, rerank, hybrid_search — accepts vector OR text |
| `vectordb/routers/documents.py` | `POST /v1/documents/upload` (multipart .txt) |
| `vectordb/routers/query.py` | `POST /v1/query` (RAG query, text only) |
| `vectordb/routers/keys.py` | API key CRUD, usage stats |
| `vectordb/routers/observability.py` | health, metrics |

## Services

| File | Role |
|------|------|
| `vectordb/services/embedding_service.py` | **Central embedding hub.** Provider ABC, SentenceTransformer/Dummy providers, LRU+Redis cache, ThreadPoolExecutor, semaphore. Public: `embed_text()`, `embed_batch()`, `embed_text_cached_async()` |
| `vectordb/services/vector_service.py` | BLOB encode/decode (`np.float32.tobytes`), L2 normalize, `success_response()`, `error_response()` |
| `vectordb/services/document_service.py` | `process_document()` — chunk + embed_batch + bulk_upsert |
| `vectordb/services/query_service.py` | `run_query()` — embed_text_cached_async + search + timing |
| `vectordb/services/chunking.py` | `chunk_text(text, chunk_size=500, overlap=50)` — pure function |

## Backends

| File | Role |
|------|------|
| `vectordb/backends/base.py` | `VectorBackend` ABC — all async methods. Domain exceptions: `CollectionNotFoundError`, `DimensionMismatchError`, `VectorNotFoundError`, `CollectionAlreadyExistsError` |
| `vectordb/backends/sqlite_hnsw.py` | SQLite + aiosqlite + HNSWlib implementation |
| `vectordb/backends/postgres_pgvector.py` | PostgreSQL + asyncpg + pgvector implementation |
| `vectordb/backends/__init__.py` | `get_backend()` FastAPI dependency (reads `request.app.state.backend`) |
| `vectordb/cache.py` | `CachingBackend` — Redis decorator wrapping any backend |

## Indexing

| File | Role |
|------|------|
| `vectordb/indexing/hnsw.py` | `HNSWIndexer` — thread-safe hnswlib wrapper |
| `vectordb/indexing/manager.py` | `IndexManager` — per-collection index lifecycle (load, persist, delete) |

## Models

| File | Role |
|------|------|
| `vectordb/models/db.py` | SQLAlchemy models: `Collection` (user_id), `Vector`, `ApiKey` (user_id), `User`, `KeyUsageLog`. `init_db()`, `get_db()` |
| `vectordb/models/schemas.py` | Pydantic request schemas. `UpsertRequest` / `SearchRequest` / `RerankRequest` accept vector OR text. `HybridSearchRequest` has optional vector. |

## Config Values (key defaults)

```
vector_dim=384, ef_construction=200, m=16, ef_query=30
embedding_provider="sentence-transformers", embedding_model="all-MiniLM-L6-v2"
chunk_size=500, chunk_overlap=50
embedding_cache_size=1000, embedding_cache_ttl=3600
max_concurrent_embeddings=4, max_query_length=1000
max_batch_size=1000, max_metadata_size=50
storage_backend="sqlite", redis_url=""
```
