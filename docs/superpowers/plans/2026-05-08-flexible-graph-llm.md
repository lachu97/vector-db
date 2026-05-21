# Flexible GraphRAG LLM Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded OpenAI graph extraction with LiteLLM so any provider (OpenAI, Gemini, Ollama, Anthropic, etc.) works; add per-collection model config and admin endpoints to test/benchmark models.

**Architecture:** LiteLLM `acompletion()` is the single extraction call — model string routes to provider. Per-collection `extraction_model` + `extraction_api_keys` (Fernet-encrypted) stored in DB. New admin endpoints: `PATCH /graph/config`, `POST /admin/graph/test-model`, `POST /admin/graph/benchmark`.

**Tech Stack:** `litellm`, `cryptography` (Fernet), SQLAlchemy (Alembic migration), FastAPI, pytest + unittest.mock

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `requirements.txt` | Add litellm, cryptography |
| Modify | `vectordb/config.py` | Remove ollama vars; add GRAPH_ENCRYPTION_KEY, provider API key vars |
| Create | `vectordb/services/graph_encryption.py` | Fernet encrypt/decrypt helpers for API keys |
| Modify | `vectordb/models/db.py` | Add extraction_model + extraction_api_keys columns to Collection |
| Create | `migrations/versions/c1d2e3f4a5b6_add_collection_extraction_config.py` | Alembic migration for 2 new columns |
| Modify | `vectordb/backends/sqlite_hnsw.py` | Update get_pending_extraction_jobs to JOIN collection config |
| Modify | `vectordb/services/graph_extraction.py` | Replace AsyncOpenAI with litellm.acompletion; new signature |
| Modify | `vectordb/models/schemas.py` | Add GraphConfigRequest/Response, TestModelRequest/Response, BenchmarkRequest/Response |
| Modify | `vectordb/routers/graph.py` | Add PATCH /graph/config; add admin_router with test-model + benchmark |
| Modify | `vectordb/app.py` | Register admin_router |
| Create | `tests/test_graph_llm_provider.py` | All new tests |
| Modify | `tests/test_graphrag.py` | Update TestLLMExtract for new llm_extract signature |

---

## Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add litellm and cryptography to requirements.txt**

Open `requirements.txt` and append after the GraphRAG section:

```
# Flexible GraphRAG LLM provider
litellm>=1.40.0
cryptography>=42.0.0
```

- [ ] **Step 2: Install**

```bash
pip install litellm cryptography
```

Expected: both install without errors.

- [ ] **Step 3: Verify importable**

```bash
python -c "import litellm; import cryptography; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(deps): add litellm and cryptography for flexible graph LLM provider"
```

---

## Task 2: Update config.py

**Files:**
- Modify: `vectordb/config.py`

- [ ] **Step 1: Write failing test**

In `tests/test_graph_llm_provider.py` (create new file):

```python
"""Tests for flexible GraphRAG LLM provider — config, encryption, extraction, endpoints."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestConfig:
    def test_new_graph_config_fields_present(self):
        """Config has encryption key and provider key fields; old ollama vars removed."""
        from vectordb.config import Settings
        s = Settings(
            _env_file=None,
            graph_encryption_key="",
            openai_api_key="sk-test",
            gemini_api_key="gem-test",
            anthropic_api_key="ant-test",
        )
        assert hasattr(s, "graph_encryption_key")
        assert hasattr(s, "gemini_api_key")
        assert hasattr(s, "anthropic_api_key")
        assert not hasattr(s, "graph_llm_provider")
        assert not hasattr(s, "graph_ollama_base_url")
        assert not hasattr(s, "graph_ollama_model")
        assert s.graph_extraction_model == "gpt-4o-mini"  # default preserved
```

- [ ] **Step 2: Run test to verify it fails**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestConfig -v
```

Expected: FAIL — `graph_llm_provider` likely still exists, new fields missing.

- [ ] **Step 3: Update config.py**

Replace the GraphRAG extraction block:

```python
    # GraphRAG extraction
    graph_extraction_model: str = "gpt-4o-mini"   # any LiteLLM model string; env: GRAPH_EXTRACTION_MODEL
    graph_encryption_key: str = ""                 # 32-byte hex; env: GRAPH_ENCRYPTION_KEY
    graph_extractor_version: str = "v1"
    graph_worker_interval_s: int = 2
    graph_worker_concurrency: int = 5
    graph_max_collections: int = 50

    # Provider API keys (server-level fallbacks; per-collection keys override these)
    openai_api_key: str = ""       # env: OPENAI_API_KEY
    gemini_api_key: str = ""       # env: GEMINI_API_KEY
    anthropic_api_key: str = ""    # env: ANTHROPIC_API_KEY
```

Remove `graph_llm_provider`, `graph_ollama_base_url`, `graph_ollama_model` if present from Task 0 partial work.

Note: `openai_api_key` already existed — keep it. Add `gemini_api_key` and `anthropic_api_key` as new fields.

- [ ] **Step 4: Run test to verify it passes**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestConfig -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vectordb/config.py tests/test_graph_llm_provider.py
git commit -m "feat(config): add graph encryption key and provider API key fields; remove ollama-specific vars"
```

---

## Task 3: Create graph_encryption.py

**Files:**
- Create: `vectordb/services/graph_encryption.py`
- Test: `tests/test_graph_llm_provider.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_graph_llm_provider.py`:

```python
class TestGraphEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt then decrypt returns original dict."""
        from vectordb.services.graph_encryption import encrypt_api_keys, decrypt_api_keys
        key_hex = "a" * 64  # 32 bytes as hex
        original = {"api_key": "sk-secret", "GEMINI_API_KEY": "gm-secret"}
        blob = encrypt_api_keys(original, key_hex)
        assert isinstance(blob, str)
        assert "sk-secret" not in blob  # encrypted
        result = decrypt_api_keys(blob, key_hex)
        assert result == original

    def test_encrypt_empty_dict(self):
        """Empty dict encrypts and decrypts cleanly."""
        from vectordb.services.graph_encryption import encrypt_api_keys, decrypt_api_keys
        key_hex = "b" * 64
        blob = encrypt_api_keys({}, key_hex)
        assert decrypt_api_keys(blob, key_hex) == {}

    def test_no_encryption_key_stores_plaintext(self):
        """When encryption key is empty, returns raw JSON (plaintext fallback)."""
        from vectordb.services.graph_encryption import encrypt_api_keys, decrypt_api_keys
        keys = {"api_key": "sk-plain"}
        blob = encrypt_api_keys(keys, encryption_key="")
        assert json.loads(blob) == keys  # readable as JSON
        assert decrypt_api_keys(blob, encryption_key="") == keys

    def test_wrong_key_raises(self):
        """Decrypting with wrong key raises an exception."""
        from vectordb.services.graph_encryption import encrypt_api_keys, decrypt_api_keys
        from cryptography.fernet import InvalidToken
        blob = encrypt_api_keys({"api_key": "secret"}, "a" * 64)
        with pytest.raises(Exception):
            decrypt_api_keys(blob, "b" * 64)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestGraphEncryption -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Create vectordb/services/graph_encryption.py**

```python
"""Fernet encryption helpers for per-collection LLM API keys."""
import base64
import json
import structlog

logger = structlog.get_logger(__name__)
_warned_no_key = False


def _make_fernet(key_hex: str):
    from cryptography.fernet import Fernet
    key_bytes = bytes.fromhex(key_hex)[:32]
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_api_keys(keys: dict, encryption_key: str) -> str:
    """Encrypt keys dict to a string blob. Falls back to plaintext JSON if no key."""
    global _warned_no_key
    if not encryption_key:
        if not _warned_no_key:
            logger.warning("graph_encryption_key_not_set_storing_plaintext")
            _warned_no_key = True
        return json.dumps(keys)
    return _make_fernet(encryption_key).encrypt(json.dumps(keys).encode()).decode()


def decrypt_api_keys(blob: str, encryption_key: str) -> dict:
    """Decrypt blob back to keys dict. Falls back to plaintext JSON if no key."""
    if not encryption_key:
        return json.loads(blob)
    return json.loads(_make_fernet(encryption_key).decrypt(blob.encode()).decode())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestGraphEncryption -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add vectordb/services/graph_encryption.py tests/test_graph_llm_provider.py
git commit -m "feat(graph): add Fernet encryption helpers for per-collection LLM API keys"
```

---

## Task 4: DB model + Alembic migration

**Files:**
- Modify: `vectordb/models/db.py` (Collection class, lines 72-83)
- Create: `migrations/versions/c1d2e3f4a5b6_add_collection_extraction_config.py`

- [ ] **Step 1: Add columns to Collection model in db.py**

In the `Collection` class (after `created_at`), add:

```python
    extraction_model = Column(String, nullable=True)       # overrides server default
    extraction_api_keys = Column(Text, nullable=True)      # Fernet-encrypted JSON blob
```

Full class after change:
```python
class Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    dim = Column(Integer, nullable=False)
    distance_metric = Column(String, nullable=False, default="cosine")
    description = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    extraction_model = Column(String, nullable=True)
    extraction_api_keys = Column(Text, nullable=True)

    vectors = relationship("Vector", back_populates="collection", cascade="all, delete-orphan")
```

- [ ] **Step 2: Generate migration**

```bash
alembic revision --autogenerate -m "add_collection_extraction_config"
```

Expected: new file created in `migrations/versions/`.

- [ ] **Step 3: Apply migration**

```bash
alembic upgrade head
```

Expected: no errors.

- [ ] **Step 4: Verify columns exist (CRITICAL — SQLite batch_alter can silently fail)**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('vectors.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(collections)')]
print(cols)
assert 'extraction_model' in cols, 'extraction_model MISSING'
assert 'extraction_api_keys' in cols, 'extraction_api_keys MISSING'
print('OK')
"
```

Expected: column names printed including `extraction_model` and `extraction_api_keys`, then `OK`.

If columns missing, add manually:
```bash
python -c "
import sqlite3
conn = sqlite3.connect('vectors.db')
conn.execute('ALTER TABLE collections ADD COLUMN extraction_model VARCHAR')
conn.execute('ALTER TABLE collections ADD COLUMN extraction_api_keys TEXT')
conn.commit()
print('manually added')
"
```

- [ ] **Step 5: Commit**

```bash
git add vectordb/models/db.py migrations/
git commit -m "feat(db): add extraction_model and extraction_api_keys columns to collections"
```

---

## Task 5: Update backend — include collection config in job results

**Files:**
- Modify: `vectordb/backends/sqlite_hnsw.py` (get_pending_extraction_jobs, ~line 1022)

- [ ] **Step 1: Write failing test**

Append to `tests/test_graph_llm_provider.py`:

```python
class TestBackendJobsIncludeCollectionConfig:
    def test_pending_jobs_include_extraction_fields(self, tmp_path):
        """get_pending_extraction_jobs returns extraction_model and extraction_api_keys."""
        import asyncio
        from vectordb.backends.sqlite_hnsw import SQLiteHNSWBackend

        backend = SQLiteHNSWBackend(db_url=f"sqlite+aiosqlite:///{tmp_path}/test.db")
        asyncio.run(backend.initialize())

        # Create collection then fake a job
        async def run():
            col = await backend.create_collection("test", 4, "cosine", user_id=None)
            # Insert a job directly via session
            from vectordb.models.db import GraphExtractionJob
            from vectordb.models.db import get_db
            db = next(get_db.__wrapped__() if hasattr(get_db, '__wrapped__') else iter([None]))
            # Use backend session factory directly
            async with backend._session_factory() as session:
                job = GraphExtractionJob(
                    collection_id=col["id"],
                    document_id="doc1",
                    chunk_id="chunk1",
                    chunk_text="Apple acquired Beats.",
                    status="pending",
                    attempt_count=0,
                    max_attempts=3,
                )
                session.add(job)
                await session.commit()

            jobs = await backend.get_pending_extraction_jobs(limit=10)
            assert len(jobs) == 1
            assert "extraction_model" in jobs[0]
            assert "extraction_api_keys" in jobs[0]

        asyncio.run(run())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestBackendJobsIncludeCollectionConfig -v
```

Expected: FAIL — `extraction_model` key not present in returned dict.

- [ ] **Step 3: Update get_pending_extraction_jobs in sqlite_hnsw.py**

Find the method at ~line 1022. Replace the query and return dict:

```python
    async def get_pending_extraction_jobs(
        self, limit: int = 10
    ) -> List[dict]:
        """Fetch pending jobs for the extraction worker, including collection LLM config."""
        from vectordb.models.db import GraphExtractionJob, Collection
        async with self._session_factory() as session:
            rows = await session.execute(
                select(GraphExtractionJob, Collection.extraction_model, Collection.extraction_api_keys)
                .join(Collection, Collection.id == GraphExtractionJob.collection_id)
                .where(
                    GraphExtractionJob.status == "pending",
                    GraphExtractionJob.attempt_count < GraphExtractionJob.max_attempts,
                )
                .order_by(GraphExtractionJob.created_at)
                .limit(limit)
            )
            results = rows.all()
            return [
                {
                    "id": j.id,
                    "collection_id": j.collection_id,
                    "document_id": j.document_id,
                    "chunk_id": j.chunk_id,
                    "chunk_text": j.chunk_text,
                    "attempt_count": j.attempt_count,
                    "extraction_model": extraction_model,
                    "extraction_api_keys": extraction_api_keys,
                }
                for j, extraction_model, extraction_api_keys in results
            ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestBackendJobsIncludeCollectionConfig -v
```

Expected: PASS

- [ ] **Step 5: Run full suite to check nothing broken**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/ -q --ignore=tests/test_phase6_cli.py --ignore=tests/test_phase6_python_sdk.py --ignore=tests/test_phase5.py 2>&1 | tail -10
```

Expected: same pass/fail count as before this task.

- [ ] **Step 6: Commit**

```bash
git add vectordb/backends/sqlite_hnsw.py tests/test_graph_llm_provider.py
git commit -m "feat(backend): include collection extraction_model and extraction_api_keys in pending job results"
```

---

## Task 6: Rewrite graph_extraction.py with LiteLLM

**Files:**
- Modify: `vectordb/services/graph_extraction.py`
- Modify: `tests/test_graphrag.py` (update TestLLMExtract)
- Test: `tests/test_graph_llm_provider.py`

- [ ] **Step 1: Write failing tests for new llm_extract signature**

Append to `tests/test_graph_llm_provider.py`:

```python
class TestLLMExtractLiteLLM:
    def test_llm_extract_no_model_returns_empty(self):
        """Empty model string returns empty lists immediately."""
        import asyncio
        from vectordb.services.graph_extraction import llm_extract
        entities, edges = asyncio.run(llm_extract("Some text.", model="", api_keys={}))
        assert entities == []
        assert edges == []

    def test_llm_extract_no_client_returns_empty(self):
        """None model returns empty lists."""
        import asyncio
        from vectordb.services.graph_extraction import llm_extract
        entities, edges = asyncio.run(llm_extract("Some text.", model=None, api_keys={}))
        assert entities == []
        assert edges == []

    def test_llm_extract_calls_litellm_with_model(self):
        """llm_extract passes model string and api_key to litellm.acompletion."""
        import asyncio
        from vectordb.services.graph_extraction import llm_extract

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"entities": [{"entity_text": "Apple", "entity_type": "ORG"}], "edges": []}'

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            entities, edges = asyncio.run(llm_extract(
                "Apple makes iPhones.",
                model="gpt-4o-mini",
                api_keys={"api_key": "sk-test"},
            ))

        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["api_key"] == "sk-test"
        assert len(entities) == 1
        assert entities[0]["entity_text"] == "Apple"
        assert edges == []

    def test_llm_extract_ollama_no_api_key(self):
        """Ollama model string passes no api_key (uses None)."""
        import asyncio
        from vectordb.services.graph_extraction import llm_extract

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"entities": [], "edges": []}'

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            asyncio.run(llm_extract("text", model="ollama/llama3.2", api_keys={}))

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get("api_key") is None

    def test_llm_extract_malformed_json_returns_empty(self):
        """Model returns non-JSON → empty lists, no exception."""
        import asyncio
        from vectordb.services.graph_extraction import llm_extract

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Sure! Here are the entities..."

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            entities, edges = asyncio.run(llm_extract("text", model="gpt-4o-mini", api_keys={}))

        assert entities == []
        assert edges == []

    def test_llm_extract_litellm_exception_returns_empty(self):
        """LiteLLM raises AuthenticationError → empty lists, no exception propagated."""
        import asyncio
        from vectordb.services.graph_extraction import llm_extract

        with patch("litellm.acompletion", new=AsyncMock(side_effect=Exception("AuthenticationError"))):
            entities, edges = asyncio.run(llm_extract("text", model="gpt-4o-mini", api_keys={"api_key": "bad"}))

        assert entities == []
        assert edges == []

    def test_resolve_api_key_openai(self):
        """OpenAI model resolves OPENAI_API_KEY from dict."""
        from vectordb.services.graph_extraction import _resolve_api_key
        keys = {"OPENAI_API_KEY": "sk-open", "GEMINI_API_KEY": "gm-key"}
        assert _resolve_api_key("gpt-4o-mini", keys) == "sk-open"

    def test_resolve_api_key_gemini(self):
        """Gemini model resolves GEMINI_API_KEY from dict."""
        from vectordb.services.graph_extraction import _resolve_api_key
        keys = {"OPENAI_API_KEY": "sk-open", "GEMINI_API_KEY": "gm-key"}
        assert _resolve_api_key("gemini/gemini-1.5-flash", keys) == "gm-key"

    def test_resolve_api_key_anthropic(self):
        """Anthropic model resolves ANTHROPIC_API_KEY from dict."""
        from vectordb.services.graph_extraction import _resolve_api_key
        keys = {"ANTHROPIC_API_KEY": "sk-ant"}
        assert _resolve_api_key("anthropic/claude-haiku-4-5", keys) == "sk-ant"

    def test_resolve_api_key_ollama_returns_none(self):
        """Ollama model returns None (no key needed)."""
        from vectordb.services.graph_extraction import _resolve_api_key
        assert _resolve_api_key("ollama/llama3.2", {"OPENAI_API_KEY": "sk"}) is None

    def test_resolve_api_key_direct_override(self):
        """api_key in dict takes precedence over provider-specific keys."""
        from vectordb.services.graph_extraction import _resolve_api_key
        keys = {"api_key": "direct-key", "OPENAI_API_KEY": "sk-other"}
        assert _resolve_api_key("gpt-4o-mini", keys) == "direct-key"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestLLMExtractLiteLLM -v
```

Expected: FAIL — `llm_extract` has wrong signature; `_resolve_api_key` doesn't exist.

- [ ] **Step 3: Rewrite graph_extraction.py**

Replace entire file content:

```python
"""
Graph extraction worker — polls graph_extraction_jobs and runs LLM extraction via LiteLLM.

Lifecycle:
  App startup → asyncio.create_task(start_extraction_worker(backend))
  Worker: polls every GRAPH_WORKER_INTERVAL_S seconds for pending jobs
  On startup: resets any stuck 'processing' jobs back to 'pending'
  LLM: extracts entities + relationships per chunk via litellm.acompletion
  Concurrency: asyncio.Semaphore(GRAPH_WORKER_CONCURRENCY) for parallel LLM calls
  Retry: up to max_attempts (default 3) per job
"""
import asyncio
import json
from typing import List, Optional, Tuple

import litellm
import structlog

from vectordb.config import get_settings
from vectordb.services.graph_manager import graph_manager

logger = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3
LLM_TIMEOUT_SECONDS = 30

# Suppress litellm's verbose success logging
litellm.suppress_debug_info = True

EXTRACTION_PROMPT = """Extract entities and relationships from the following text.

Return a JSON object with exactly this structure:
{{
  "entities": [
    {{"entity_text": "Apple", "entity_type": "ORG"}}
  ],
  "edges": [
    {{"source_entity_text": "Apple", "relation_type": "acquired", "target_entity_text": "Beats", "weight": 1.0}}
  ]
}}

Entity types: PERSON, ORG, CONCEPT, PLACE, EVENT
Keep entity_text concise (1-4 words). Only include meaningful relationships.
If no entities found, return {{"entities": [], "edges": []}}.

Text:
{chunk_text}"""


def _resolve_api_key(model: str, api_keys: dict) -> Optional[str]:
    """Pick the right API key for the given model from the provided keys dict."""
    if not api_keys:
        return None
    if "api_key" in api_keys:
        return api_keys["api_key"]
    m = model.lower()
    if m.startswith("ollama/") or m.startswith("ollama_chat/"):
        return None
    if m.startswith("gemini/") or m.startswith("google/"):
        return api_keys.get("GEMINI_API_KEY")
    if m.startswith("anthropic/") or "claude" in m:
        return api_keys.get("ANTHROPIC_API_KEY")
    # Default: OpenAI or unknown provider
    return api_keys.get("OPENAI_API_KEY")


async def llm_extract(
    chunk_text: str,
    model: Optional[str],
    api_keys: dict,
) -> Tuple[List[dict], List[dict]]:
    """
    Call LiteLLM to extract entities and relationships from chunk_text.
    Returns (entities_list, edges_list). Falls back to ([], []) on any failure.
    """
    if not model:
        return [], []

    prompt = EXTRACTION_PROMPT.format(chunk_text=chunk_text)
    api_key = _resolve_api_key(model, api_keys)

    call_kwargs = dict(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert knowledge graph extractor. "
                    "Always respond with valid JSON only, no markdown, no explanation."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=1024,
    )
    if api_key is not None:
        call_kwargs["api_key"] = api_key

    try:
        response = await asyncio.wait_for(
            litellm.acompletion(**call_kwargs),
            timeout=LLM_TIMEOUT_SECONDS,
        )

        raw = response.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("llm_extract_json_parse_error", model=model, raw=raw[:200])
            return [], []

        entities = data.get("entities", [])
        edges = data.get("edges", [])
        if not isinstance(entities, list):
            entities = []
        if not isinstance(edges, list):
            edges = []

        return entities, edges

    except asyncio.TimeoutError:
        logger.warning("llm_extract_timeout", model=model, chunk_len=len(chunk_text))
        return [], []
    except Exception as e:
        logger.warning("llm_extract_error", model=model, error=str(e))
        return [], []


def _build_api_keys_from_settings(settings) -> dict:
    """Build server-level api_keys dict from settings (used as fallback)."""
    keys = {}
    if settings.openai_api_key:
        keys["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.gemini_api_key:
        keys["GEMINI_API_KEY"] = settings.gemini_api_key
    if settings.anthropic_api_key:
        keys["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    return keys


async def _process_one_job(job: dict, backend, settings, semaphore: asyncio.Semaphore) -> None:
    """Process a single extraction job under the concurrency semaphore."""
    async with semaphore:
        job_id = job["id"]
        await backend.update_extraction_job(job_id, "processing")

        try:
            # Resolve model: collection-level overrides server default
            model = job.get("extraction_model") or settings.graph_extraction_model

            # Resolve API keys: decrypt collection-level keys, merge with server fallbacks
            from vectordb.services.graph_encryption import decrypt_api_keys
            server_keys = _build_api_keys_from_settings(settings)
            collection_keys = {}
            if job.get("extraction_api_keys"):
                try:
                    collection_keys = decrypt_api_keys(job["extraction_api_keys"], settings.graph_encryption_key)
                except Exception as e:
                    logger.warning("llm_key_decrypt_error", job_id=job_id, error=str(e))

            # Collection-level keys override server keys
            merged_keys = {**server_keys, **collection_keys}

            entities, edges = await llm_extract(job["chunk_text"], model, merged_keys)

            from vectordb.models.db import get_db
            db = next(get_db())
            try:
                for e in entities:
                    e["document_id"] = job["document_id"]
                    e["chunk_id"] = job["chunk_id"]
                    e["extractor_version"] = settings.graph_extractor_version
                    e["model_name"] = model
                    e.setdefault("vector_external_id", None)
                    e.setdefault("extraction_prompt_hash", None)

                for edge in edges:
                    edge["document_id"] = job["document_id"]
                    edge["chunk_id"] = job["chunk_id"]
                    edge["extractor_version"] = settings.graph_extractor_version
                    edge["model_name"] = model

                await graph_manager.add_entities_edges(job["collection_id"], db, entities, edges)
            finally:
                db.close()

            await backend.update_extraction_job(job_id, "completed")
            logger.info("extraction_job_completed", job_id=job_id, model=model, entities=len(entities), edges=len(edges))

        except Exception as e:
            logger.warning("extraction_job_failed", job_id=job_id, error=str(e))
            attempt_number = job.get("attempt_count", 0) + 1
            if attempt_number < MAX_ATTEMPTS:
                await backend.update_extraction_job(job_id, "pending")
            else:
                await backend.update_extraction_job(job_id, "failed", error_message=str(e))


async def _process_pending_jobs(backend, settings, semaphore: asyncio.Semaphore) -> None:
    """Process up to 10 pending jobs in one pass."""
    jobs = await backend.get_pending_extraction_jobs(limit=10)
    if not jobs:
        return
    tasks = [_process_one_job(job, backend, settings, semaphore) for job in jobs]
    await asyncio.gather(*tasks, return_exceptions=True)


async def start_extraction_worker(backend) -> None:
    """
    Background asyncio task. Call via asyncio.create_task() at app startup.
    - Resets stuck 'processing' jobs on first run (crash recovery)
    - Polls for pending jobs every graph_worker_interval_s seconds
    - Runs LLM extraction with semaphore concurrency control
    - Updates job status: processing → completed / failed (with retry)
    """
    settings = get_settings()
    semaphore = asyncio.Semaphore(settings.graph_worker_concurrency)

    await asyncio.sleep(1)

    try:
        await backend.reset_processing_jobs()
        logger.info(
            "extraction_worker_started",
            concurrency=settings.graph_worker_concurrency,
            default_model=settings.graph_extraction_model,
        )
    except Exception as e:
        logger.warning("extraction_worker_reset_error", error=str(e))

    while True:
        try:
            await _process_pending_jobs(backend, settings, semaphore)
        except Exception as e:
            logger.warning("extraction_worker_error", error=str(e))
        await asyncio.sleep(settings.graph_worker_interval_s)
```

- [ ] **Step 4: Update existing TestLLMExtract in tests/test_graphrag.py**

Find `class TestLLMExtract` in `tests/test_graphrag.py`. Replace the entire class with:

```python
class TestLLMExtract:

    def test_llm_extract_no_model_returns_empty(self):
        """Returns empty lists when model is empty string."""
        from vectordb.services.graph_extraction import llm_extract
        entities, edges = asyncio.run(llm_extract("some text", model="", api_keys={}))
        assert entities == []
        assert edges == []

    def test_llm_extract_no_client_returns_empty(self):
        """Returns empty lists when model is None."""
        from vectordb.services.graph_extraction import llm_extract
        entities, edges = asyncio.run(llm_extract("some text", model=None, api_keys={}))
        assert entities == []
        assert edges == []

    def test_llm_extract_empty_text_returns_empty(self):
        """Returns empty lists for empty text with no model."""
        from vectordb.services.graph_extraction import llm_extract
        entities, edges = asyncio.run(llm_extract("", model="", api_keys={}))
        assert entities == []
        assert edges == []
```

Remove the old Ollama/OpenAI specific tests that tested `response_format` (they are superseded by `TestLLMExtractLiteLLM` in the new test file).

- [ ] **Step 5: Run new tests**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestLLMExtractLiteLLM -v
```

Expected: all PASS.

- [ ] **Step 6: Run updated TestLLMExtract**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graphrag.py::TestLLMExtract -v
```

Expected: 3 PASS.

- [ ] **Step 7: Run full suite**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/ -q --ignore=tests/test_phase6_cli.py --ignore=tests/test_phase6_python_sdk.py --ignore=tests/test_phase5.py 2>&1 | tail -10
```

Expected: same or better pass count.

- [ ] **Step 8: Commit**

```bash
git add vectordb/services/graph_extraction.py tests/test_graphrag.py tests/test_graph_llm_provider.py
git commit -m "feat(graph): replace OpenAI client with LiteLLM universal adapter; per-collection model + key resolution"
```

---

## Task 7: Add schemas

**Files:**
- Modify: `vectordb/models/schemas.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_graph_llm_provider.py`:

```python
class TestGraphSchemas:
    def test_graph_config_request_schema(self):
        """GraphConfigRequest accepts model and api_keys."""
        from vectordb.models.schemas import GraphConfigRequest
        r = GraphConfigRequest(model="ollama/llama3.2", api_keys={"api_key": "x"})
        assert r.model == "ollama/llama3.2"
        assert r.api_keys == {"api_key": "x"}

    def test_graph_config_request_all_optional(self):
        """GraphConfigRequest works with no fields (partial update)."""
        from vectordb.models.schemas import GraphConfigRequest
        r = GraphConfigRequest()
        assert r.model is None
        assert r.api_keys is None

    def test_test_model_request_schema(self):
        """TestModelRequest requires model and text."""
        from vectordb.models.schemas import TestModelRequest
        r = TestModelRequest(model="gpt-4o-mini", text="Apple acquired Beats.")
        assert r.model == "gpt-4o-mini"
        assert r.api_keys == {}

    def test_benchmark_request_max_models(self):
        """BenchmarkRequest rejects more than 5 models."""
        from vectordb.models.schemas import BenchmarkRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BenchmarkRequest(models=["m1", "m2", "m3", "m4", "m5", "m6"], text="text")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestGraphSchemas -v
```

Expected: FAIL — schemas don't exist.

- [ ] **Step 3: Add schemas to vectordb/models/schemas.py**

Append at the end of the file:

```python
class GraphConfigRequest(BaseModel):
    model: Optional[str] = None       # LiteLLM model string, e.g. "ollama/llama3.2"
    api_keys: Optional[Dict[str, str]] = None  # provider API keys, encrypted at rest


class GraphConfigResponse(BaseModel):
    model: Optional[str]
    api_keys_set: bool                # True if encrypted keys stored; never returns raw keys


class TestModelRequest(BaseModel):
    model: str
    text: str
    api_keys: Dict[str, str] = {}


class TestModelResponse(BaseModel):
    model: str
    entities: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    timing_ms: float
    error: Optional[str] = None


class BenchmarkRequest(BaseModel):
    models: List[str]
    text: str
    api_keys: Dict[str, str] = {}

    @field_validator("models")
    @classmethod
    def max_five_models(cls, v):
        if len(v) > 5:
            raise ValueError("max 5 models per benchmark request")
        return v


class BenchmarkResponse(BaseModel):
    results: List[TestModelResponse]
```

Also add `field_validator` to the imports at top of schemas.py if not already present:
```python
from pydantic import BaseModel, field_validator
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestGraphSchemas -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add vectordb/models/schemas.py tests/test_graph_llm_provider.py
git commit -m "feat(schemas): add GraphConfig, TestModel, Benchmark request/response schemas"
```

---

## Task 8: Add PATCH /graph/config endpoint

**Files:**
- Modify: `vectordb/routers/graph.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_graph_llm_provider.py`:

```python
class TestGraphConfigEndpoint:
    def test_patch_graph_config_sets_model(self, client):
        """PATCH /graph/config stores model on collection."""
        # Create collection first
        client.post("/v1/collections", json={"name": "cfg-test", "dim": 4}, headers={"x-api-key": "test-key"})
        resp = client.patch(
            "/v1/collections/cfg-test/graph/config",
            json={"model": "ollama/llama3.2"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["model"] == "ollama/llama3.2"
        assert data["api_keys_set"] is False

    def test_patch_graph_config_sets_api_keys(self, client):
        """PATCH /graph/config encrypts and stores api_keys."""
        client.post("/v1/collections", json={"name": "cfg-keys", "dim": 4}, headers={"x-api-key": "test-key"})
        resp = client.patch(
            "/v1/collections/cfg-keys/graph/config",
            json={"model": "gpt-4o-mini", "api_keys": {"OPENAI_API_KEY": "sk-test"}},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["api_keys_set"] is True

    def test_patch_graph_config_404_on_unknown_collection(self, client):
        """Returns error for unknown collection."""
        resp = client.patch(
            "/v1/collections/no-such/graph/config",
            json={"model": "gpt-4o-mini"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.json()["error"]["code"] == 404
```

The `client` fixture comes from `tests/conftest.py` — it's already available.

- [ ] **Step 2: Run tests to verify they fail**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestGraphConfigEndpoint -v
```

Expected: FAIL — endpoint doesn't exist (404).

- [ ] **Step 3: Add PATCH /graph/config to graph.py**

Add the following imports at the top of `vectordb/routers/graph.py`:

```python
from vectordb.models.schemas import (
    # ... existing imports ...
    GraphConfigRequest,
    GraphConfigResponse,
    TestModelRequest,
    TestModelResponse,
    BenchmarkRequest,
    BenchmarkResponse,
)
from vectordb.services.graph_encryption import encrypt_api_keys, decrypt_api_keys
```

Add the endpoint after `graph_status`:

```python
@router.patch("/{name}/graph/config")
async def graph_config_update(
    name: str,
    req: GraphConfigRequest,
    backend: VectorBackend = Depends(get_backend),
    auth: ApiKeyInfo = Depends(require_pro_or_scale),
):
    """Set per-collection LLM model and encrypted API keys for graph extraction."""
    col = await backend.get_collection(name, user_id=auth.user_id)
    if not col:
        return error_response(404, f"Collection '{name}' not found")

    settings = get_settings()

    from vectordb.models.db import Collection, get_db as get_sync_db
    db: Session = next(get_sync_db())
    try:
        collection = db.query(Collection).filter(Collection.id == col["id"]).first()
        if req.model is not None:
            collection.extraction_model = req.model
        if req.api_keys is not None:
            collection.extraction_api_keys = encrypt_api_keys(req.api_keys, settings.graph_encryption_key)
        db.commit()
        api_keys_set = collection.extraction_api_keys is not None
        model = collection.extraction_model
    finally:
        db.close()

    return success_response(GraphConfigResponse(
        model=model,
        api_keys_set=api_keys_set,
    ).model_dump())
```

- [ ] **Step 4: Add missing imports to graph.py**

Ensure these are present at the top:

```python
from vectordb.config import get_settings
from vectordb.models.db import get_db
```

(`get_db` was already imported — add `get_settings` if missing.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestGraphConfigEndpoint -v
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add vectordb/routers/graph.py tests/test_graph_llm_provider.py
git commit -m "feat(graph): add PATCH /collections/{name}/graph/config to set per-collection LLM model and API keys"
```

---

## Task 9: Add test-model and benchmark admin endpoints

**Files:**
- Modify: `vectordb/routers/graph.py` (add admin_router)
- Modify: `vectordb/app.py` (register admin_router)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_graph_llm_provider.py`:

```python
class TestAdminGraphEndpoints:
    def test_test_model_returns_entities(self, client):
        """POST /admin/graph/test-model calls llm_extract and returns results."""
        from unittest.mock import patch, AsyncMock

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"entities": [{"entity_text": "Apple", "entity_type": "ORG"}], "edges": []}'
        )
        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            resp = client.post(
                "/v1/admin/graph/test-model",
                json={"model": "gpt-4o-mini", "text": "Apple makes iPhones.", "api_keys": {}},
                headers={"x-api-key": "test-key"},
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["model"] == "gpt-4o-mini"
        assert len(data["entities"]) == 1
        assert data["error"] is None

    def test_test_model_error_captured(self, client):
        """POST /admin/graph/test-model captures LiteLLM errors in error field."""
        from unittest.mock import patch, AsyncMock

        with patch("litellm.acompletion", new=AsyncMock(side_effect=Exception("AuthenticationError"))):
            resp = client.post(
                "/v1/admin/graph/test-model",
                json={"model": "gpt-4o-mini", "text": "text.", "api_keys": {"api_key": "bad"}},
                headers={"x-api-key": "test-key"},
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["entities"] == []
        assert "AuthenticationError" in data["error"]

    def test_benchmark_runs_all_models(self, client):
        """POST /admin/graph/benchmark returns results for each model."""
        from unittest.mock import patch, AsyncMock

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"entities": [], "edges": []}'

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            resp = client.post(
                "/v1/admin/graph/benchmark",
                json={
                    "models": ["gpt-4o-mini", "ollama/llama3.2"],
                    "text": "Apple acquired Beats.",
                    "api_keys": {},
                },
                headers={"x-api-key": "test-key"},
            )
        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        assert len(results) == 2
        model_names = [r["model"] for r in results]
        assert "gpt-4o-mini" in model_names
        assert "ollama/llama3.2" in model_names

    def test_benchmark_rejects_more_than_5_models(self, client):
        """POST /admin/graph/benchmark returns error for >5 models."""
        resp = client.post(
            "/v1/admin/graph/benchmark",
            json={"models": ["m1", "m2", "m3", "m4", "m5", "m6"], "text": "text"},
            headers={"x-api-key": "test-key"},
        )
        # FastAPI returns 422 for pydantic validation failure
        assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestAdminGraphEndpoints -v
```

Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Add admin_router to graph.py**

At the top of `vectordb/routers/graph.py`, add after the existing `router` definition:

```python
admin_router = APIRouter(prefix="/v1/admin", tags=["graph-admin"])
```

At the bottom of `graph.py`, add both endpoints:

```python
@admin_router.post("/graph/test-model")
async def graph_test_model(
    req: TestModelRequest,
    auth: ApiKeyInfo = Depends(require_admin),
):
    """Test a single LLM model for graph extraction — returns entities, edges, and timing."""
    import time
    from vectordb.services.graph_extraction import llm_extract, _resolve_api_key

    settings = get_settings()
    server_keys = {}
    if settings.openai_api_key:
        server_keys["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.gemini_api_key:
        server_keys["GEMINI_API_KEY"] = settings.gemini_api_key
    if settings.anthropic_api_key:
        server_keys["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    merged_keys = {**server_keys, **req.api_keys}

    error_msg = None
    t0 = time.perf_counter()
    try:
        entities, edges = await llm_extract(req.text, req.model, merged_keys)
    except Exception as e:
        entities, edges = [], []
        error_msg = str(e)
    timing_ms = round((time.perf_counter() - t0) * 1000, 2)

    return success_response(TestModelResponse(
        model=req.model,
        entities=entities,
        edges=edges,
        timing_ms=timing_ms,
        error=error_msg,
    ).model_dump())


@admin_router.post("/graph/benchmark")
async def graph_benchmark(
    req: BenchmarkRequest,
    auth: ApiKeyInfo = Depends(require_admin),
):
    """Benchmark multiple LLM models in parallel — returns side-by-side extraction results."""
    import time
    from vectordb.services.graph_extraction import llm_extract

    settings = get_settings()
    server_keys = {}
    if settings.openai_api_key:
        server_keys["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.gemini_api_key:
        server_keys["GEMINI_API_KEY"] = settings.gemini_api_key
    if settings.anthropic_api_key:
        server_keys["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    merged_keys = {**server_keys, **req.api_keys}

    async def run_one(model: str) -> TestModelResponse:
        error_msg = None
        t0 = time.perf_counter()
        try:
            entities, edges = await llm_extract(req.text, model, merged_keys)
        except Exception as e:
            entities, edges = [], []
            error_msg = str(e)
        timing_ms = round((time.perf_counter() - t0) * 1000, 2)
        return TestModelResponse(model=model, entities=entities, edges=edges, timing_ms=timing_ms, error=error_msg)

    results = await asyncio.gather(*[run_one(m) for m in req.models], return_exceptions=False)

    return success_response(BenchmarkResponse(results=list(results)).model_dump())
```

Also add `require_admin` to the imports at the top of graph.py:
```python
from vectordb.auth import ApiKeyInfo, require_admin, require_pro_or_scale, require_scale
```

- [ ] **Step 4: Register admin_router in app.py**

Find where `graph.router` is included in `vectordb/app.py`. Add `graph.admin_router` right after it:

```python
from vectordb.routers import graph
app.include_router(graph.router)
app.include_router(graph.admin_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/test_graph_llm_provider.py::TestAdminGraphEndpoints -v
```

Expected: 4 PASS.

- [ ] **Step 6: Run full suite**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/ -q --ignore=tests/test_phase6_cli.py --ignore=tests/test_phase6_python_sdk.py --ignore=tests/test_phase5.py 2>&1 | tail -10
```

Expected: ≥390 pass, 1 pre-existing fail (test_root), no new failures.

- [ ] **Step 7: Commit**

```bash
git add vectordb/routers/graph.py vectordb/app.py tests/test_graph_llm_provider.py
git commit -m "feat(graph): add /admin/graph/test-model and /admin/graph/benchmark endpoints for model comparison"
```

---

## Task 10: Update .env documentation + final verification

**Files:**
- Modify: `CLAUDE.md` (env table)
- Modify: `vector-db-web/CLAUDE.md` (Backend Changelog)

- [ ] **Step 1: Update env table in CLAUDE.md**

In the `## Environment Variables` table, replace the `GRAPH_EXTRACTION_MODEL` row and add new rows:

```markdown
| GRAPH_EXTRACTION_MODEL | gpt-4o-mini | LiteLLM model string for extraction (any provider) |
| GRAPH_ENCRYPTION_KEY | (empty) | 32-byte hex key for encrypting per-collection API keys |
| OPENAI_API_KEY | (empty) | Server-level OpenAI key (fallback for all collections) |
| GEMINI_API_KEY | (empty) | Server-level Gemini key |
| ANTHROPIC_API_KEY | (empty) | Server-level Anthropic key |
```

Remove `GRAPH_LLM_PROVIDER`, `GRAPH_OLLAMA_BASE_URL`, `GRAPH_OLLAMA_MODEL` rows if they were added.

Generate `GRAPH_ENCRYPTION_KEY` with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

- [ ] **Step 2: Add Backend Changelog entry in vector-db-web/CLAUDE.md**

Add a new row to the changelog table:

```markdown
| 2026-05-08 | **Flexible GraphRAG LLM provider (LiteLLM).** Per-collection model config via `PATCH /v1/collections/{name}/graph/config` (Pro/Scale). New admin endpoints: `POST /v1/admin/graph/test-model` (test one model), `POST /v1/admin/graph/benchmark` (parallel multi-model comparison). Supports OpenAI, Gemini, Anthropic, Ollama, and 100+ providers via LiteLLM. Server-level keys in `.env`; per-collection keys encrypted in DB. | Add model selector UI in collection settings for Pro/Scale users. Add a "Test Model" panel and "Benchmark" comparison table in admin section. |
```

- [ ] **Step 3: Final full test run**

```bash
EMBEDDING_PROVIDER=dummy pytest tests/ -v --ignore=tests/test_phase6_cli.py --ignore=tests/test_phase6_python_sdk.py --ignore=tests/test_phase5.py 2>&1 | tail -20
```

Expected: ≥390 pass.

- [ ] **Step 4: Final commit**

```bash
git add CLAUDE.md vector-db-web/CLAUDE.md
git commit -m "docs: update env vars and frontend changelog for flexible GraphRAG LLM provider"
```
