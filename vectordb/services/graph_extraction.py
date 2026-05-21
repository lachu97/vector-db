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


def _build_server_keys(settings) -> dict:
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
            model = job.get("extraction_model") or settings.graph_extraction_model

            from vectordb.services.graph_encryption import decrypt_api_keys
            server_keys = _build_server_keys(settings)
            collection_keys = {}
            if job.get("extraction_api_keys"):
                try:
                    collection_keys = decrypt_api_keys(
                        job["extraction_api_keys"], settings.graph_encryption_key
                    )
                except Exception as e:
                    logger.warning("llm_key_decrypt_error", job_id=job_id, error=str(e))

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
            logger.info(
                "extraction_job_completed",
                job_id=job_id,
                model=model,
                entities=len(entities),
                edges=len(edges),
            )

        except Exception as e:
            logger.warning("extraction_job_failed", job_id=job_id, error=str(e))
            attempt_number = job.get("attempt_count", 0) + 1
            if attempt_number < MAX_ATTEMPTS:
                await backend.update_extraction_job(job_id, "pending")
                logger.info("extraction_job_requeued", job_id=job_id, attempt_number=attempt_number)
            else:
                await backend.update_extraction_job(job_id, "failed", error_message=str(e))
                logger.warning("extraction_job_exhausted", job_id=job_id, attempt_number=attempt_number)


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
