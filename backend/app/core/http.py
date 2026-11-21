import asyncio
import logging
import time
from contextvars import ContextVar

import httpx

from app.core.config import get_settings

log = logging.getLogger("wodiva.http")

SOURCE_TIMEOUT_S = {
    "uldk": 10.0,
    "egib": 8.0,
    "openmeteo": 10.0,
    "openmeteo_archive": 25.0,
    "imgw": 10.0,
    "soilgrids": 10.0,
}

timings: ContextVar[dict[str, float] | None] = ContextVar("timings", default=None)

_client: httpx.AsyncClient | None = None


class SourceError(Exception):
    def __init__(self, source: str, message: str):
        super().__init__(f"{source}: {message}")
        self.source = source


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            headers={"User-Agent": "Wodiva/0.1 (HackNation 2026, KOWR)"},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=40),
        )
    return _client


def set_client(client: httpx.AsyncClient | None) -> None:
    global _client
    _client = client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def record_timing(source: str, seconds: float) -> None:
    store = timings.get()
    if store is not None:
        store[source] = round(store.get(source, 0.0) + seconds, 3)
    log.info("source=%s time=%.2fs", source, seconds)


async def fetch(
    source: str,
    url: str,
    params: dict | list | None = None,
    retries: int = 2,
    timeout: float | None = None,
) -> httpx.Response:
    limit = timeout or SOURCE_TIMEOUT_S.get(source, get_settings().http_timeout_s)
    started = time.perf_counter()
    last_error = "unknown"
    try:
        for attempt in range(retries + 1):
            try:
                response = await get_client().get(url, params=params, timeout=limit)
                if response.status_code >= 500 or response.status_code == 429:
                    last_error = f"HTTP {response.status_code}"
                else:
                    response.raise_for_status()
                    return response
            except httpx.HTTPStatusError as exc:
                raise SourceError(source, f"HTTP {exc.response.status_code}") from exc
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))
        raise SourceError(source, last_error)
    finally:
        record_timing(source, time.perf_counter() - started)
