# Hot Paths

## Critical Path 1: Query (latency-sensitive, P95 < 80ms target)

```
embed_text_cached_async(query)  ->  backend.search()
```

- Embedding is the bottleneck. Cache hit = ~0ms. Cache miss = ~30-50ms.
- Cache tiers: Redis (sha256 key, msgpack, TTL 3600s) -> LRU (1000 entries) -> compute
- Query normalization BEFORE cache lookup: lowercase, strip, remove punct, collapse spaces
- Non-blocking: semaphore + ThreadPoolExecutor + `asyncio.get_running_loop().run_in_executor()`
- ef_query=30 (tuned down from 50 for speed)

## Critical Path 2: Upsert with text (throughput-sensitive)

```
embed_text(text)  ->  backend.upsert()
```

- Single insert: `embed_text()` (sync, uncached — each doc is unique)
- Bulk insert: `embed_batch()` (sync, batched — SentenceTransformer batches efficiently)
- Text auto-populates `content` field for hybrid word search (if content not explicit)

## Critical Path 3: Document upload (batch throughput)

```
chunk_text()  ->  embed_batch(chunks)  ->  backend.bulk_upsert()
```

- Chunking: 500 chars, 50 overlap, pure Python
- Embedding: batch call to provider (single GPU/CPU batch operation)
- Storage: reuses existing bulk_upsert (batched DB commit + batched index insertion)

## Rules

1. **NEVER bypass embedding_service** — all text->vector MUST go through it
2. **NEVER block async endpoints** — query-time embedding uses `embed_text_cached_async()` only
3. **ALWAYS use caching for queries** — `embed_text_cached_async()`, never `embed_text()`
4. **NEVER use caching for inserts** — each document is unique, caching wastes memory
5. **NEVER call model.encode() directly** — only inside `SentenceTransformerProvider`
6. **NEVER import SentenceTransformer outside embedding_service.py**

## Response Pattern

All endpoints return:
```json
{"status": "success", "data": {...}, "error": null}
{"status": "error", "data": null, "error": {"code": 404, "message": "..."}}
```

Via `success_response()` / `error_response()` from `vector_service.py`. HTTP status is always 200 (except auth: 401/403).

## Multi-Tenancy Scoping

- `ApiKeyInfo.user_id` determines scope. `None` = superadmin (sees all).
- Collections filtered by: `user_id == auth.user_id OR collection.user_id IS NULL`
- All collection-scoped endpoints call `_check_collection_access(backend, name, user_id)` before proceeding

## Text OR Vector Input

All upsert/search/rerank/hybrid_search schemas accept EITHER:
- `"vector": [0.1, 0.2, ...]` — used as-is
- `"text": "some query"` — auto-embedded via embedding_service

Pydantic `model_validator` ensures at least one is provided. If both given, vector takes precedence.
Exception: `HybridSearchRequest` requires `query_text` always; `vector` is optional (auto-embedded from query_text).
