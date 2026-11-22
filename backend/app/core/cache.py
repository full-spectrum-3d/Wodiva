import json
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.core.config import get_settings

TTL_S = {
    "uldk": 30 * 86400,
    "parquet": 30 * 86400,
    "egib": 30 * 86400,
    "openmeteo": 3 * 3600,
    "openmeteo_archive": 30 * 86400,
    "imgw_archive": 7 * 86400,
    "imgw_now": 1800,
    "imgw_missing": 86400,
    "soilgrids": 365 * 86400,
    "uug": 30 * 86400,
    "default": 86400,
}


class Cache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL NOT NULL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS cache_expires ON cache(expires)")
        self._db.commit()

    @staticmethod
    def key(source: str, *parts: Any) -> str:
        return "|".join([source, *[str(p) for p in parts]])

    def get(self, key: str) -> Any | None:
        with self._lock:
            row = self._db.execute("SELECT value, expires FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None or row[1] < time.time():
            return None
        return json.loads(row[0])

    def set(self, key: str, value: Any, source: str = "default") -> None:
        ttl = TTL_S.get(source, TTL_S["default"])
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires) VALUES (?, ?, ?)",
                (key, json.dumps(value, default=str), time.time() + ttl),
            )
            self._db.commit()

    def purge_expired(self, batch: int = 5000) -> int:
        # partiami, z lockiem zwalnianym między nimi: get/set z pętli zdarzeń nie czekają na cały purge
        total = 0
        while True:
            with self._lock:
                n = self._db.execute(
                    "DELETE FROM cache WHERE rowid IN (SELECT rowid FROM cache WHERE expires < ? LIMIT ?)",
                    (time.time(), batch),
                ).rowcount
                self._db.commit()
            total += n
            if n < batch:
                return total

    async def get_or_fetch(self, source: str, parts: tuple, fetch: Callable[[], Awaitable[Any]]) -> Any:
        key = self.key(source, *parts)
        hit = self.get(key)
        if hit is not None:
            return hit
        value = await fetch()
        if value is not None:
            self.set(key, value, source)
        return value


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache(get_settings().cache_path)
    return _cache


def set_cache(cache: Cache) -> None:
    global _cache
    _cache = cache
