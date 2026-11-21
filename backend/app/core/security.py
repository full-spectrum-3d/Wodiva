import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings

LIMITED_PATHS = ("/api/analyze", "/api/assistant", "/api/parcel")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int | None = None):
        super().__init__(app)
        self.per_minute = per_minute or get_settings().rate_limit_per_minute
        self.hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(LIMITED_PATHS):
            ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
                request.client.host if request.client else "unknown"
            )
            now = time.monotonic()
            window = self.hits[ip]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.per_minute:
                return JSONResponse({"detail": "Zbyt wiele zapytań. Spróbuj ponownie za minutę."}, status_code=429)
            window.append(now)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
