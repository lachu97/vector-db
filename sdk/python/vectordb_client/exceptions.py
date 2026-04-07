"""VectorDB SDK exceptions."""


class VectorDBError(Exception):
    """Base exception for all VectorDB SDK errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class NotFoundError(VectorDBError):
    """Resource not found (HTTP 404)."""


class AlreadyExistsError(VectorDBError):
    """Resource already exists (HTTP 409)."""


class DimensionMismatchError(VectorDBError):
    """Vector dimension does not match collection dimension (HTTP 400)."""


class AuthenticationError(VectorDBError):
    """Invalid or missing API key (HTTP 401/403)."""


class RateLimitError(VectorDBError):
    """Too many requests (HTTP 429)."""


class ValidationError(VectorDBError):
    """Request validation failed (HTTP 422)."""
