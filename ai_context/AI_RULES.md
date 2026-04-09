# AI Rules (MANDATORY)

**Follow these rules strictly. No exceptions.**

## Context Loading

1. **NEVER scan the full codebase** — use `ai_context/` files only
2. **ALWAYS read all `ai_context/` files FIRST** before touching any code
3. **ONLY open files listed in `file_roles.md`** for the current task
4. **ASK the user before opening any unlisted file** — do not explore on your own

## Architecture

5. **NEVER bypass embedding_service** — all text-to-vector conversion goes through it
6. **NEVER add embedding logic to routers, backends, or vector_service**
7. **NEVER call model.encode() directly** — only inside embedding_service providers
8. **NEVER import SentenceTransformer outside embedding_service.py**
9. **NEVER modify the VectorBackend ABC interface** without updating ALL implementations (sqlite, postgres, cache)
10. **NEVER modify indexing layer** (hnsw.py, manager.py) unless explicitly asked

## Async Safety

11. **NEVER use sync embedding in async query endpoints** — always `embed_text_cached_async()`
12. **NEVER block the event loop** — use `run_in_executor` for CPU-bound work
13. **ALWAYS use the existing semaphore** for concurrency control

## API Contracts

14. **NEVER change response shape** — `{status, data, error}` envelope is fixed
15. **NEVER return HTTP 4xx from business logic** — use `error_response(code, msg)` which returns HTTP 200
16. **Auth errors (401/403) are the ONLY HTTP error codes** raised directly
17. **Schemas accept vector OR text** — both paths must work, vector takes precedence if both given

## Data Flow

18. **Insert-time embedding**: `embed_text()` (sync) or `embed_batch()` (sync, batched)
19. **Query-time embedding**: `embed_text_cached_async()` (async, cached, non-blocking)
20. **NEVER cache insert embeddings** — documents are unique
21. **ALWAYS cache query embeddings** — queries repeat

## Multi-Tenancy

22. **ALL collection operations MUST pass user_id** from `auth.user_id`
23. **user_id=None means superadmin** — sees everything, used by bootstrap key
24. **ALWAYS call _check_collection_access()** before collection-scoped operations

## Testing

25. **ALL new code MUST have tests** — no exceptions
26. **Tests use EMBEDDING_PROVIDER=dummy** — no model download
27. **Run full suite after changes** — `pytest tests/ -v --ignore=tests/test_phase6_cli.py --ignore=tests/test_phase6_python_sdk.py --ignore=tests/test_phase5.py`

## Code Style

28. **DO NOT duplicate logic** — reuse existing helpers (success_response, error_response, _check_collection_access)
29. **DO NOT add features beyond what's asked**
30. **DO NOT modify backend interface for router-level concerns**
