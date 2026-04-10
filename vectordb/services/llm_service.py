# vectordb/services/llm_service.py
"""Minimal LLM answer generation for RAG /v1/ask endpoint."""
import asyncio

import structlog

from vectordb.config import get_settings

logger = structlog.get_logger(__name__)

_client = None

_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the question using ONLY the context provided below.\n"
    "If the answer cannot be found in the context, respond with "
    '"I don\'t know based on the available information."\n'
    "Do not use any outside knowledge."
)

MAX_CONTEXT_CHARS = 3000
LLM_TIMEOUT_SECONDS = 10


def _get_client():
    """Lazy singleton for AsyncOpenAI client."""
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    from openai import AsyncOpenAI
    _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def generate_answer(query: str, context: str) -> str:
    """Generate an answer using the LLM. Returns fallback string on error."""
    client = _get_client()
    if client is None:
        return f"[LLM not configured] Retrieved {len(context)} chars of context for: {query}"

    settings = get_settings()
    prompt = f"Context:\n{context}\n\nQuestion: {query}"

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=512,
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        answer = response.choices[0].message.content
        if not answer or not answer.strip():
            answer = "I couldn't generate a reliable answer from the available context."
        return answer.strip()
    except asyncio.TimeoutError:
        logger.error("llm_timeout", query=query, timeout=LLM_TIMEOUT_SECONDS)
        return "Answer generation timed out. Please try again."
    except Exception as e:
        logger.error("llm_error", query=query, error=str(e))
        return "An error occurred while generating the answer. Sources are still available below."
