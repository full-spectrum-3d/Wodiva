import asyncio
import re
import threading
import time
from datetime import UTC, datetime
from functools import lru_cache

import duckdb
from shapely import wkb

from app.core.config import get_settings
from app.core.http import record_timing
from app.core.schemas import DataSource, SourceStatus

ID_CANDIDATES = ("idDzialki", "id_dzialki", "identyfikator", "identyfikatorDzialki", "ID_DZIALKI", "id")
GEOM_CANDIDATES = ("geometry", "geom", "the_geom", "wkb_geometry", "msGeometry")
_lock = threading.Lock()


def data_source(status: SourceStatus = SourceStatus.ok, note: str | None = None) -> DataSource:
    return DataSource(
        name="EGiB – eksport działek 0_dzialki.parquet (Geoportal opendata)",
        url=get_settings().parcels_parquet_url,
        license="Dane publiczne GUGiK, bezpłatne",
        retrieved_at=datetime.now(UTC),
        status=status,
        note=note,
    )


def _source() -> str:
    settings = get_settings()
    local = settings.parcels_parquet_local
    return str(local) if local and local.exists() else settings.parcels_parquet_url


@lru_cache
def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    return con


@lru_cache
def _schema(source: str) -> tuple[str, str, str]:
    rows = _connection().execute(f"DESCRIBE SELECT * FROM read_parquet('{source}')").fetchall()
    names = {r[0]: r[1] for r in rows}
    lower = {n.lower(): n for n in names}
    id_col = next((lower[c.lower()] for c in ID_CANDIDATES if c.lower() in lower), None)
    geom_col = next((lower[c.lower()] for c in GEOM_CANDIDATES if c.lower() in lower), None)
    if id_col is None or geom_col is None:
        raise LookupError(f"nie rozpoznano kolumn w parquet: {list(names)[:20]}")
    return id_col, geom_col, names[geom_col]


def _lookup(parcel_id: str) -> dict | None:
    if not re.fullmatch(r"[0-9A-Za-z_./]{5,60}", parcel_id):
        return None
    source = _source()
    with _lock:
        id_col, geom_col, _ = _schema(source)
        row = (
            _connection()
            .execute(
                f'SELECT "{id_col}", "{geom_col}" FROM read_parquet(\'{source}\') WHERE "{id_col}" = ? LIMIT 1',
                [parcel_id],
            )
            .fetchone()
        )
    if row is None:
        return None
    raw = row[1]
    geom = wkb.loads(bytes(raw)) if isinstance(raw, bytes | bytearray | memoryview) else None
    if geom is None:
        return None
    teryt = parcel_id.split(".")[0] if "." in parcel_id else None
    return {
        "id": row[0],
        "teryt": teryt,
        "voivodeship": None,
        "county": None,
        "commune": None,
        "region": None,
        "parcel": parcel_id.rsplit(".", 1)[-1],
        "geom_wkt": geom.wkt,
    }


async def by_id(parcel_id: str) -> dict | None:
    started = time.perf_counter()
    try:
        return await asyncio.wait_for(asyncio.to_thread(_lookup, parcel_id), timeout=25)
    finally:
        record_timing("parquet", time.perf_counter() - started)
