# vectordb/backends/__init__.py
from fastapi import Request
from vectordb.backends.base import VectorBackend


async def get_backend(request: Request) -> VectorBackend:
    """FastAPI dependency: return the app-level backend from app.state."""
    return request.app.state.backend
