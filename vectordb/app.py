# vectordb/app.py

import asyncio
import traceback
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vectordb.config import get_settings
from vectordb.logging_config import configure_logging
from vectordb.models.db import init_db
from vectordb.metrics import MetricsMiddleware
from vectordb.middleware import RateLimitMiddleware
from vectordb.services.vector_service import error_response
from vectordb.routers import (
    auth, collections, vectors, search,
    keys, observability, documents, query, usage
)
from vectordb.tracing import setup_tracing
from fastapi import FastAPI
# ------------------------------------------------------------------
# Settings & logging
# ------------------------------------------------------------------
settings = get_settings()
configure_logging(
    log_format=settings.log_format,
    log_level=settings.log_level
)
logger = structlog.get_logger(__name__)

# ------------------------------------------------------------------
# Backend factory
# ------------------------------------------------------------------
def _create_backend(settings):
    if settings.storage_backend == "postgres":
        from vectordb.backends.postgres_pgvector import PostgresVectorBackend
        logger.info("backend_selected", type="postgres+pgvector")
        return PostgresVectorBackend(settings.db_url, settings)
    else:
        from vectordb.backends.sqlite_hnsw import SQLiteHNSWBackend
        logger.info("backend_selected", type="sqlite+hnsw")
        return SQLiteHNSWBackend(settings.db_url, settings)


def _wrap_cache(backend, settings):
    if not settings.redis_url:
        return backend

    from vectordb.cache import CachingBackend
    logger.info(
        "cache_enabled",
        redis_url=settings.redis_url,
        ttl=settings.cache_ttl
    )
    return CachingBackend(
        backend,
        settings.redis_url,
        settings.cache_ttl
    )

# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        observability.reset_start_time()

        await app.state.backend.startup()

        from vectordb.services.embedding_service import initialize_provider
        initialize_provider()

        from vectordb.cleanup import cleanup_loop
        asyncio.create_task(cleanup_loop())

        logger.info("app_startup_complete")

    except Exception as e:
        logger.error(
            "startup_failed",
            error=str(e),
            traceback=traceback.format_exc()
        )

    yield

    try:
        await app.state.backend.shutdown()
        logger.info("app_shutdown_complete")
    except Exception as e:
        logger.error("shutdown_failed", error=str(e))

# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
app = FastAPI(
    title="Vector DB",
    version="3.0.0",
    lifespan=lifespan
)

# backend must exist before routers
_backend = _create_backend(settings)
_backend = _wrap_cache(_backend, settings)
app.state.backend = _backend

# ------------------------------------------------------------------
# Tracing
# ------------------------------------------------------------------
setup_tracing(app, None, settings)

# ------------------------------------------------------------------
# Middleware
# ------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(MetricsMiddleware)

app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=settings.rate_limit_per_minute
)

# ------------------------------------------------------------------
# Routers
# ------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(collections.router)
app.include_router(vectors.router)
app.include_router(search.router)
app.include_router(keys.router)
app.include_router(usage.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(observability.router)

# ------------------------------------------------------------------
# Root
# ------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "message": "Welcome to Vector DB",
        "docs": "/docs",
        "backend": settings.storage_backend,
        "cache": "redis" if settings.redis_url else "none",
    }

@app.get("/health")
def health():
    return {"status": "ok"}

# ------------------------------------------------------------------
# Global exception handler
# ------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        error=str(exc),
        path=str(request.url.path)
    )
    return JSONResponse(
        status_code=500,
        content=error_response(500, str(exc))
    )