import hashlib
import json
import sqlite3
import threading
import time
from typing import Any

from app.land.settings import var_dir

DAY = 86400.0


class LandCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(var_dir() / "land_cache.sqlite", check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value BLOB, kind TEXT, expires REAL)"
        )
        self._conn.commit()

    @staticmethod
    def make_key(source: str, *parts: Any) -> str:
        raw = json.dumps([source, *parts], sort_keys=True, default=str)
        return source + ":" + hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        with self._lock:
            row = self._conn.execute("SELECT value, kind, expires FROM cache WHERE key=?", (key,)).fetchone()
        if row is None or (row[2] is not None and row[2] < time.time()):
            return None
        return json.loads(row[0]) if row[1] == "json" else row[0]

    def set(self, key: str, value: Any, ttl_s: float | None) -> None:
        if isinstance(value, bytes | bytearray):
            payload, kind = bytes(value), "bytes"
        else:
            payload, kind = json.dumps(value, default=str), "json"
        expires = None if ttl_s is None else time.time() + ttl_s
        with self._lock:
            self._conn.execute("REPLACE INTO cache VALUES (?, ?, ?, ?)", (key, payload, kind, expires))
            self._conn.commit()


_cache: LandCache | None = None


def get_cache() -> LandCache:
    global _cache
    if _cache is None:
        _cache = LandCache()
    return _cache


class _Proxy:
    def __getattr__(self, name):
        return getattr(get_cache(), name)


cache = _Proxy()
