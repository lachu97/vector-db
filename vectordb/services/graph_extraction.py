# vectordb/services/graph_extraction.py
"""
Graph extraction worker — polls graph_extraction_jobs and runs LLM extraction.

Lifecycle:
  App startup → asyncio.create_task(start_extraction_worker(backend))
  Worker: polls every GRAPH_WORKER_INTERVAL_S seconds for pending jobs
  On startup: resets any stuck 'processing' jobs back to 'pending'
  LLM: extracts entities + relationships per chunk
  Concurrency: asyncio.Semaphore(GRAPH_WORKER_CONCURRENCY) for parallel LLM calls
  Retry: up to max_attempts (default 3) per job
"""
import asyncio
import json
from typing import List, Tuple

import structlog

from vectordb.config import get_settings
from vectordb.services.graph_manager import graph_manager

logger = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3
LLM_TIMEOUT_SECONDS = 30

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

async def llm_extract(chunk_text: str, settings, client=None) -> Tuple[List[dict], List[dict]]:
    """
    Call OpenAI to extract entities and relationships from chunk_text.
    Returns (entities_list, edges_list).
    Falls back to ([], []) if OpenAI key not configured or call fails.
    """
    if not settings.openai_api_key or client is None:
        return [], []

    prompt = EXTRACTION_PROMPT.format(chunk_text=chunk_text)

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=settings.graph_extraction_model,
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
                response_format={"type": "json_object"},
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )

        raw = response.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("llm_extract_json_parse_error", raw=raw[:200])
            return [], []

        entities = data.get("entities", [])
        edges = data.get("edges", [])

        if not isinstance(entities, list):
            entities = []
        if not isinstance(edges, list):
            edges = []

        return entities, edges

    except asyncio.TimeoutError:
        logger.warning("llm_extract_timeout", chunk_len=len(chunk_text))
        return [], []
    except Exception as e:
        logger.warning("llm_extract_error", error=str(e))
        return [], []


async def _process_one_job(job: dict, backend, settings, semaphore: asyncio.Semaphore, client) -> None:
    """Process a single extraction job under the concurrency semaphore."""
    async with semaphore:
        job_id = job["id"]

        # Mark as processing (this increments attempt_count in the DB)
        await backend.update_extraction_job(job_id, "processing")

        try:
            entities, edges = await llm_extract(job["chunk_text"], settings, client)

            # Resolve collection_id to sync DB session for graph_manager
            from vectordb.models.db import get_db

            db = next(get_db())
            try:
                # Attach document/chunk provenance to each entity
                for e in entities:
                    e["document_id"] = job["document_id"]
                    e["chunk_id"] = job["chunk_id"]
                    e["extractor_version"] = settings.graph_extractor_version
                    e["model_name"] = settings.graph_extraction_model
                    e.setdefault("vector_external_id", None)
                    e.setdefault("extraction_prompt_hash", None)

                for edge in edges:
                    edge["document_id"] = job["document_id"]
                    edge["chunk_id"] = job["chunk_id"]
                    edge["extractor_version"] = settings.graph_extractor_version
                    edge["model_name"] = settings.graph_extraction_model

                await graph_manager.add_entities_edges(
                    job["collection_id"], db, entities, edges
                )
            finally:
                db.close()

            await backend.update_extraction_job(job_id, "completed")
            logger.info(
                "extraction_job_completed",
                job_id=job_id,
                entities=len(entities),
                edges=len(edges),
            )

        except Exception as e:
            logger.warning("extraction_job_failed", job_id=job_id, error=str(e))

            # attempt_number is 1-indexed: job["attempt_count"] holds the count
            # before this attempt; setting status='processing' increments it in the DB,
            # so the current attempt is attempt_count + 1.
            attempt_number = job.get("attempt_count", 0) + 1
            if attempt_number < MAX_ATTEMPTS:
                # Re-queue for another attempt
                await backend.update_extraction_job(job_id, "pending")
                logger.info(
                    "extraction_job_requeued",
                    job_id=job_id,
                    attempt_number=attempt_number,
                    max_attempts=MAX_ATTEMPTS,
                )
            else:
                # Exhausted retries — mark permanently failed
                await backend.update_extraction_job(
                    job_id, "failed", error_message=str(e)
                )
                logger.warning(
                    "extraction_job_exhausted",
                    job_id=job_id,
                    attempt_number=attempt_number,
                )


async def _process_pending_jobs(backend, settings, semaphore: asyncio.Semaphore, client) -> None:
    """Process up to 10 pending jobs in one pass."""
    jobs = await backend.get_pending_extraction_jobs(limit=10)
    if not jobs:
        return

    tasks = [_process_one_job(job, backend, settings, semaphore, client) for job in jobs]
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

    # Initialize the OpenAI client once here — avoids global mutable state and
    # race conditions that a lazy singleton would introduce in an async context.
    client = None
    if settings.openai_api_key:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Give the backend thread time to finish startup before the first poll
    await asyncio.sleep(1)

    # Crash recovery: reset any jobs stuck in 'processing' from a previous crash
    try:
        await backend.reset_processing_jobs()
        logger.info("extraction_worker_started", concurrency=settings.graph_worker_concurrency)
    except Exception as e:
        logger.warning("extraction_worker_reset_error", error=str(e))

    while True:
        try:
            await _process_pending_jobs(backend, settings, semaphore, client)
        except Exception as e:
            logger.warning("extraction_worker_error", error=str(e))
        await asyncio.sleep(settings.graph_worker_interval_s)
