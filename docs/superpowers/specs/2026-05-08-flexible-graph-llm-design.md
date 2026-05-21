# Flexible GraphRAG LLM Provider — Design Spec

**Date:** 2026-05-08
**Status:** Approved

---

## Goal

Replace the hardcoded OpenAI client in graph extraction with a LiteLLM-based universal adapter. Users choose any LLM (OpenAI, Gemini, Ollama, Anthropic, etc.) per-collection, change it at runtime via API, test and benchmark models before committing.

---

## Architecture

```
graph_extraction.py
  └── llm_extract(chunk_text, model, api_keys)
        └── litellm.acompletion(model=model, api_key=..., ...)
              └── routes to: OpenAI | Gemini | Ollama | Anthropic | 100+ others

Extraction worker (start_extraction_worker)
  └── per job: reads collection's extraction_model + extraction_api_keys from DB
        └── falls back to server-default GRAPH_EXTRACTION_MODEL if collection has none
        └── calls llm_extract with resolved model + keys

Collections table (2 new columns)
  ├── extraction_model: VARCHAR (nullable) — overrides server default
  └── extraction_api_keys: TEXT (nullable) — Fernet-encrypted JSON blob

New endpoints
  ├── PATCH /v1/collections/{name}/graph/config  — set model + keys at runtime
  ├── POST  /v1/admin/graph/test-model            — single model test
  └── POST  /v1/admin/graph/benchmark             — parallel multi-model comparison
```

---

## Components

### 1. LiteLLM integration (`graph_extraction.py`)

- Remove `AsyncOpenAI` client entirely
- `llm_extract(chunk_text, model, api_keys)` calls `litellm.acompletion()`
- `api_keys` dict passed as `**kwargs` environment overrides to LiteLLM
- Drop `response_format` — LiteLLM handles JSON mode per-provider where supported; prompt instructs JSON-only output
- `LLM_TIMEOUT_SECONDS = 30` preserved
- Fallback: any exception → log warning → return `([], [])`

### 2. Encryption (`graph_encryption.py` — new file)

- `cryptography` lib, Fernet (AES-128-CBC + HMAC)
- `encrypt_api_keys(keys: dict) -> str` — JSON → Fernet encrypt → base64 string
- `decrypt_api_keys(blob: str) -> dict` — reverse
- Key from `GRAPH_ENCRYPTION_KEY` env var (32-byte hex)
- If `GRAPH_ENCRYPTION_KEY` not set: store plaintext + emit warning log once at startup

### 3. Config (`.env` / `config.py`)

New vars:
```
GRAPH_EXTRACTION_MODEL=gpt-4o-mini   # server-level default
GRAPH_ENCRYPTION_KEY=<32-byte hex>   # for encrypting per-collection API keys
OPENAI_API_KEY=...                   # server-level fallback for OpenAI
GEMINI_API_KEY=...                   # server-level fallback for Gemini
ANTHROPIC_API_KEY=...                # server-level fallback for Anthropic
```

Remove: `GRAPH_LLM_PROVIDER`, `GRAPH_OLLAMA_BASE_URL`, `GRAPH_OLLAMA_MODEL`

Ollama needs no API key — set model as `ollama/llama3.2`, worker connects to `http://localhost:11434`.

### 4. DB migration

Alembic migration adds 2 columns to `collections`:
- `extraction_model VARCHAR` nullable
- `extraction_api_keys TEXT` nullable

After migration, verify with `PRAGMA table_info(collections)` per CLAUDE.md rule.

### 5. Extraction worker update

`_process_one_job` resolves model + keys per job:
```python
model = job["extraction_model"] or settings.graph_extraction_model
api_keys = decrypt_api_keys(job["extraction_api_keys"]) if job["extraction_api_keys"] else {}
entities, edges = await llm_extract(chunk_text, model, api_keys)
```

Worker startup no longer initializes a client — client is stateless (LiteLLM call per job).

### 6. `PATCH /v1/collections/{name}/graph/config` (Pro/Scale)

Request:
```json
{ "model": "gemini/gemini-1.5-flash", "api_keys": { "GEMINI_API_KEY": "..." } }
```
- Both fields optional — omit to leave unchanged
- `api_keys` encrypted before storage; never returned in responses (nulled out)
- Returns updated collection graph config: `{ "model": "gemini/gemini-1.5-flash", "api_keys_set": true }`

### 7. `POST /v1/admin/graph/test-model` (admin role)

Request:
```json
{ "model": "ollama/llama3.2", "text": "Apple acquired Beats in 2014.", "api_keys": {} }
```
Response:
```json
{ "model": "ollama/llama3.2", "entities": [...], "edges": [...], "timing_ms": 240, "error": null }
```
- Calls `llm_extract` directly — does not touch any collection or DB
- `error` field populated if LiteLLM raises, entities/edges empty

### 8. `POST /v1/admin/graph/benchmark` (admin role)

Request:
```json
{
  "models": ["gpt-4o-mini", "ollama/llama3.2", "gemini/gemini-1.5-flash"],
  "text": "Apple acquired Beats in 2014.",
  "api_keys": { "GEMINI_API_KEY": "..." }
}
```
Response:
```json
{
  "results": [
    { "model": "gpt-4o-mini", "entities": [...], "edges": [...], "timing_ms": 340, "error": null },
    { "model": "ollama/llama3.2", "entities": [...], "edges": [...], "timing_ms": 890, "error": null },
    { "model": "gemini/gemini-1.5-flash", "entities": [], "edges": [], "timing_ms": 0, "error": "AuthenticationError" }
  ]
}
```
- All models run in parallel via `asyncio.gather`
- Max 5 models per request
- `api_keys` in request merged with server-level env keys (request keys win)

---

## Error Handling

| Error | Behavior |
|-------|----------|
| LiteLLM `AuthenticationError` | Return `([], [])` in extraction; `error` field in test/benchmark |
| LiteLLM `BadRequestError` (unknown model) | Same |
| JSON parse failure from model | Return `([], [])` — log raw response (truncated) |
| `asyncio.TimeoutError` | Return `([], [])` — log timeout |
| Missing `GRAPH_ENCRYPTION_KEY` | Warn at startup, store/read plaintext |

---

## Testing

- `test_llm_extract_litellm_*` — mock `litellm.acompletion`, verify model/key routing
- `test_per_collection_model_override` — collection with custom model uses it; falls back to default when null
- `test_graph_config_endpoint` — PATCH stores encrypted keys, GET config shows `api_keys_set: true` not raw keys
- `test_benchmark_parallel` — all models called, results in same order as input, errors isolated per model
- `test_encryption_roundtrip` — encrypt → decrypt returns original dict
- Existing `TestLLMExtract` tests updated for new signature

---

## Requirements

New dependency: `litellm`, `cryptography`

Add to `requirements.txt`.

---

## Out of Scope

- LiteLLM proxy sidecar
- Per-user (vs per-collection) model config
- Model cost tracking / token counting
- Automatic model selection / scoring
