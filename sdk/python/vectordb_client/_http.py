"""Shared HTTP utilities: error parsing and response handling."""

from __future__ import annotations
from typing import Any

from vectordb_client.exceptions import (
    VectorDBError,
    NotFoundError,
    AlreadyExistsError,
    DimensionMismatchError,
    AuthenticationError,
    RateLimitError,
    ValidationError,
)

_STATUS_MAP = {
    400: VectorDBError,
    401: AuthenticationError,
    403: AuthenticationError,
    404: NotFoundError,
    409: AlreadyExistsError,
    422: ValidationError,
    429: RateLimitError,
}


def _raise_for_response(status_code: int, body: dict) -> None:
    """Raise the appropriate SDK exception based on HTTP/body status + error body.

    The VectorDB API returns HTTP 200 for all responses, embedding the real
    error code in ``body["error"]["code"]``.  This function accepts either
    the HTTP-level status (for transport errors) or the body-level code.
    """
    error = body.get("error") or {}
    # Prefer the body-embedded error code over the HTTP status code.
    code = error.get("code", status_code)
    message = error.get("message", f"HTTP {code}")
    detail = error.get("detail", "")
    if detail:
        message = f"{message}: {detail}"

    # Special-case dimension mismatch (comes as 400)
    if code == 400 and "dimension" in message.lower():
        raise DimensionMismatchError(message, status_code=code)

    exc_cls = _STATUS_MAP.get(code, VectorDBError)
    raise exc_cls(message, status_code=code)


def _check_body_error(body: dict) -> None:
    """Check the body envelope and raise if status == 'error'."""
    if body.get("status") == "error":
        _raise_for_response(0, body)


def _unwrap(body: dict) -> Any:
    """Return the `data` payload from a standard API response envelope."""
    _check_body_error(body)
    return body.get("data", body)
