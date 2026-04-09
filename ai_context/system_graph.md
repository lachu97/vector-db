# System Graph

## Architecture

```
Client Request
    |
    v
[FastAPI Routers] ---- HTTP layer only, no business logic
    |
    v
[Auth] ---- x-api-key -> ApiKeyInfo(key, name, role, user_id)
    |
    v
[Services]
    |
    +---> embedding_service --- text -> vector, caching, async
    |         |
    |         +---> Provider ABC (SentenceTransformer | Dummy)
    |         +---> Cache: Redis (msgpack, sha256) -> LRU (1000) -> compute
    |         +---> Concurrency: ThreadPoolExecutor + asyncio.Semaphore
    |
    +---> vector_service --- encode/decode BLOB, normalize L2, index helpers
    |
    +---> document_service --- chunk + embed_batch + bulk_upsert
    |
    +---> query_service --- embed_text_cached_async + search + timing
    |
    v
[Backends] ---- VectorBackend ABC (async interface)
    |
    +---> SQLiteHNSWBackend (sqlite + aiosqlite + HNSWlib)
    +---> PostgresVectorBackend (postgres + asyncpg + pgvector)
    +---> CachingBackend (Redis decorator, wraps either backend)
    |
    v
[Indexing] ---- HNSWIndexer (thread-safe) + IndexManager (per-collection)
    |
    v
[Database] ---- SQLAlchemy models (Collection, Vector, ApiKey, User)
```

## Component Boundaries

| Component | Does | Does NOT |
|-----------|------|----------|
| Routers | HTTP, validation, auth, resolve text->vector | Business logic, DB access |
| embedding_service | text->vector, caching, async concurrency | Storage, indexing |
| vector_service | BLOB encode/decode, L2 normalize, response helpers | Embedding, DB queries |
| Backends | All DB/index CRUD (async) | Embedding, HTTP |
| Indexing | HNSW add/query/persist | DB operations |

## Key Singletons (initialized at startup)

- `app.state.backend` — VectorBackend instance (set before lifespan)
- `embedding_service._provider` — EmbeddingProvider (set in `initialize_provider()`)
- `embedding_service._semaphore` — asyncio.Semaphore(max_concurrent_embeddings)
- `embedding_service._executor` — ThreadPoolExecutor
- `embedding_service._redis_client` — optional Redis for embedding cache
