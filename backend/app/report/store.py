import sqlite3
import threading
from datetime import UTC, datetime, timedelta

from app.core.schemas import Report
from app.land.settings import var_dir

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(var_dir() / "reports.sqlite", check_same_thread=False, timeout=30)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, created TEXT, body TEXT, map BLOB)")
        _conn.execute("CREATE TABLE IF NOT EXISTS overlays (id TEXT, name TEXT, png BLOB, PRIMARY KEY (id, name))")
        _conn.commit()
    return _conn


def save(report: Report, map_png: bytes | None) -> None:
    with _lock:
        _db().execute(
            "REPLACE INTO reports VALUES (?, ?, ?, ?)",
            (report.id, report.created_at.isoformat(), report.model_dump_json(), map_png),
        )
        _db().commit()


def load(report_id: str) -> Report | None:
    with _lock:
        row = _db().execute("SELECT body FROM reports WHERE id=?", (report_id,)).fetchone()
    return Report.model_validate_json(row[0]) if row else None


def load_map(report_id: str) -> bytes | None:
    with _lock:
        row = _db().execute("SELECT map FROM reports WHERE id=?", (report_id,)).fetchone()
    return row[0] if row else None


def save_overlay(report_id: str, name: str, png: bytes) -> None:
    with _lock:
        _db().execute("REPLACE INTO overlays VALUES (?, ?, ?)", (report_id, name, png))
        _db().commit()


def load_overlay(report_id: str, name: str) -> bytes | None:
    with _lock:
        row = _db().execute("SELECT png FROM overlays WHERE id=? AND name=?", (report_id, name)).fetchone()
    return row[0] if row else None


def purge(older_than_days: int) -> int:
    # created to ISO z +00:00 (Report.created_at w UTC), więc porównanie tekstowe jest chronologiczne
    cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
    with _lock:
        ids = [(row[0],) for row in _db().execute("SELECT id FROM reports WHERE created < ?", (cutoff,))]
        # tylko nakładki usuwanych raportów: persist zapisuje nakładkę przed raportem, więc „osierocona” może być świeża
        _db().executemany("DELETE FROM overlays WHERE id = ?", ids)
        _db().executemany("DELETE FROM reports WHERE id = ?", ids)
        _db().commit()
    return len(ids)
