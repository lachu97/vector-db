# vectordb/middleware.py
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter per API key (in-memory).

    Tracks request timestamps per API key over a 60-second window.
    Requests without an API key are not rate-limited here (auth will
    reject them first anyway).

    Note: In-memory state is per-process. With multiple Gunicorn workers
    the effective limit is requests_per_minute * workers per key. A Redis-
    backed limiter is planned for Phase 5.
    """

    def __init__(self, app, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._windows: dict = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        api_key = request.headers.get("x-api-key")
        if api_key:
            now = time.monotonic()
            window = 60.0
            timestamps = self._windows[api_key]

            # Drop timestamps outside the sliding window
            cutoff = now - window
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)

            if len(timestamps) >= self.requests_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={
                        "status": "error",
                        "error": {
                            "code": 429,
                            "message": "Rate limit exceeded. Try again later.",
                        },
                    },
                )
            timestamps.append(now)

        return await call_next(request)
