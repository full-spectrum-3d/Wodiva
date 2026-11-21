import sqlite3
import time
from datetime import UTC, datetime, timedelta

from app.core import cache as cache_module
from app.report import store


def test_cache_purge_drops_only_expired():
    cache = cache_module.get_cache()
    cache.set("fresh", {"a": 1})
    cache._db.execute("INSERT INTO cache VALUES ('old', '1', ?)", (time.time() - 10,))
    assert cache.purge_expired() == 1
    assert cache.get("fresh") == {"a": 1}


def test_report_purge_removes_old_reports_and_their_overlays(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(store, "var_dir", lambda: tmp_path)
    db = store._db()
    old = (datetime.now(UTC) - timedelta(days=100)).isoformat()
    new = datetime.now(UTC).isoformat()
    db.executemany("INSERT INTO reports VALUES (?, ?, '{}', NULL)", [("old", old), ("new", new)])
    db.executemany("INSERT INTO overlays VALUES (?, 'ndvi', x'00')", [("old",), ("new",), ("in_progress",)])
    assert store.purge(90) == 1
    assert [r[0] for r in db.execute("SELECT id FROM reports")] == ["new"]
    # nakładka zapisana przed raportem (persist w toku) zostaje
    assert sorted(r[0] for r in db.execute("SELECT id FROM overlays")) == ["in_progress", "new"]
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert isinstance(db, sqlite3.Connection)
    db.close()


def test_cache_purge_works_in_batches():
    cache = cache_module.get_cache()
    rows = [(f"k{i}", "1", time.time() - 10) for i in range(7)]
    cache._db.executemany("INSERT INTO cache VALUES (?, ?, ?)", rows)
    assert cache.purge_expired(batch=3) == 7
