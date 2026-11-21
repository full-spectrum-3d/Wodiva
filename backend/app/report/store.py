import sqlite3
import threading

from app.core.schemas import Report
from app.land.settings import var_dir

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(var_dir() / "reports.sqlite", check_same_thread=False)
        _conn.execute("CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, created TEXT, body TEXT, map BLOB)")
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
