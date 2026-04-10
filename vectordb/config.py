# vectordb/config.py
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    api_key: str = "test-key"
    vector_dim: int = 384
    index_path: str = "data/index.bin"
    max_elements: int = 10_000
    ef_construction: int = 200
    m: int = 16
    ef_query: int = 30
    db_url: str = Field(
        default="sqlite:///./vectors.db",
        alias="DATABASE_URL"
    )
    port: int = 8000
    workers: int = 4

    # CORS
    cors_origins: List[str] = ["*"]

    # Rate limiting (requests per minute per API key)
    rate_limit_per_minute: int = 100

    # Request validation hardening
    max_vector_dim: int = 10_000
    max_metadata_size: int = 50    # max keys in a metadata dict
    max_batch_size: int = 1_000   # max items in bulk_upsert / batch_delete

    # Logging
    log_format: str = "json"      # "json" or "console"
    log_level: str = "INFO"

    # OpenTelemetry tracing
    otel_enabled: bool = False
    otel_service_name: str = "vector-db"
    otel_endpoint: str = ""       # e.g. "http://localhost:4318" for OTLP HTTP

    # RAG / Embedding
    embedding_provider: str = "sentence-transformers"  # "sentence-transformers" | "dummy"
    embedding_model: str = "all-MiniLM-L6-v2"          # 384-dim, matches vector_dim
    chunk_size: int = 500
    chunk_overlap: int = 50
    embedding_cache_size: int = 1000
    embedding_cache_ttl: int = 3600                     # Redis cache TTL in seconds
    max_concurrent_embeddings: int = 4
    max_query_length: int = 1000

    # LLM (for /v1/ask RAG answer generation)
    openai_api_key: str = ""              # env: OPENAI_API_KEY
    llm_model: str = "gpt-4o-mini"        # env: LLM_MODEL

    # Storage backend — Phase 5
    storage_backend: str = "sqlite"   # "sqlite" or "postgres"
    redis_url: str = ""               # e.g. "redis://localhost:6379/0"
    cache_ttl: int = 60              # search cache TTL in seconds

    model_config = {"env_file": ".env", "extra": "ignore"}


_settings_cache = None


def get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache
