import asyncio
import re
import threading
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import duckdb
from shapely import wkb, wkt
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from app.core.config import get_settings
from app.core.http import record_timing
from app.core.schemas import DataSource, SourceStatus
from app.water.geo import lonlat_to_2180

ID_CANDIDATES = ("idDzialki", "id_dzialki", "identyfikator", "identyfikatorDzialki", "ID_DZIALKI", "id")
GEOM_CANDIDATES = ("geometry", "geom", "the_geom", "wkb_geometry", "msGeometry")
_lock = threading.Lock()
_index_lock = threading.Lock()
VOIVODESHIPS = {f"{n:02d}" for n in range(2, 33, 2)}
NATIONAL_FILE = "/0_dzialki.parquet"
PARCEL_ID = re.compile(r"[0-9A-Za-z_./]{5,60}")
INDEX_NAME = "EGiB – lokalny indeks"
INDEX_COLUMNS = (
    "id_dzialki, numer_dzialki, nazwa_obrebu, numer_jednostki, nazwa_gminy, data, klasouzytki_egib, geometry"
)
SEARCH_COLUMNS = "id_dzialki, numer_dzialki, nazwa_obrebu, nazwa_gminy, numer_jednostki"


def region_url(parcel_id: str) -> str:
    url = get_settings().parcels_parquet_url
    code = parcel_id[:2]
    if code in VOIVODESHIPS and url.endswith(NATIONAL_FILE):
        return url.removesuffix(NATIONAL_FILE) + f"/{code}_dzialki.parquet"
    return url


def data_source(status: SourceStatus = SourceStatus.ok, note: str | None = None, parcel_id: str = "") -> DataSource:
    url = region_url(parcel_id)
    return DataSource(
        name=f"EGiB – eksport działek {url.rsplit('/', 1)[-1]} (Geoportal opendata)",
        url=url,
        license="Dane publiczne GUGiK, bezpłatne",
        retrieved_at=datetime.now(UTC),
        status=status,
        note=note,
    )


def _source(parcel_id: str) -> str:
    local = get_settings().parcels_parquet_local
    return str(local) if local and local.is_file() else region_url(parcel_id)


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
    if not PARCEL_ID.fullmatch(parcel_id):
        return None
    source = _source(parcel_id)
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


def index_dir() -> Path | None:
    folder = get_settings().parcels_index_dir
    return folder if folder and folder.is_dir() else None


def _index_files() -> list[Path]:
    folder = index_dir()
    return sorted(folder.glob("woj_*.parquet")) if folder else []


def _index_file(code: str) -> Path | None:
    folder = index_dir()
    if folder is None or code not in VOIVODESHIPS:
        return None
    target = folder / f"woj_{code}.parquet"
    return target if target.is_file() else None


@lru_cache
def _index_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def _index_query(sql: str, params: list) -> list[dict]:
    with _index_lock:
        cursor = _index_connection().execute(sql, params)
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]


def _geometry(raw) -> BaseGeometry | None:
    if isinstance(raw, bytes | bytearray | memoryview):
        return wkb.loads(bytes(raw))
    if isinstance(raw, str):
        return wkt.loads(raw)
    return None


def _index_row(row: dict, geom: BaseGeometry, path: Path) -> dict:
    return {
        "id": row["id_dzialki"],
        "teryt": row.get("numer_jednostki"),
        "voivodeship": None,
        "county": None,
        "commune": row.get("nazwa_gminy"),
        "region": row.get("nazwa_obrebu"),
        "parcel": row.get("numer_dzialki"),
        "geom_wkt": geom.wkt,
        "index_file": str(path),
        "index_data": str(row["data"]) if row.get("data") else None,
        "land_codes": row.get("klasouzytki_egib") or None,
    }


def _index_by_id(parcel_id: str) -> dict | None:
    target = _index_file(parcel_id[:2])
    if target is None or not PARCEL_ID.fullmatch(parcel_id):
        return None
    rows = _index_query(
        f"SELECT {INDEX_COLUMNS} FROM read_parquet('{target.as_posix()}') WHERE id_dzialki = ? LIMIT 1",
        [parcel_id],
    )
    if not rows:
        return None
    geom = _geometry(rows[0]["geometry"])
    return _index_row(rows[0], geom, target) if geom is not None else None


def _index_by_point(lat: float, lon: float) -> dict | None:
    files = _index_files()
    if not files:
        return None
    x, y = lonlat_to_2180(lon, lat)
    point = Point(x, y)
    for path in files:
        rows = _index_query(
            f"SELECT {INDEX_COLUMNS} FROM read_parquet('{path.as_posix()}') "
            "WHERE xmin <= ? AND xmax >= ? AND ymin <= ? AND ymax >= ?",
            [x, x, y, y],
        )
        for row in rows:
            geom = _geometry(row["geometry"])
            if geom is not None and geom.covers(point):
                return _index_row(row, geom, path)
    return None


def _search(commune: str, region: str, number: str, limit: int) -> list[dict]:
    files = _index_files()
    if not files:
        raise LookupError("brak lokalnego indeksu działek")
    clauses = ["nazwa_gminy ILIKE ?"]
    params: list = [f"{commune}%"]
    if region:
        clauses.append("nazwa_obrebu ILIKE ?")
        params.append(f"{region}%")
    if number:
        clauses.append("numer_dzialki LIKE ?")
        params.append(f"{number}%")
    pattern = (files[0].parent / "woj_*.parquet").as_posix()
    rows = _index_query(
        f"SELECT {SEARCH_COLUMNS} FROM read_parquet('{pattern}') WHERE {' AND '.join(clauses)} "
        "ORDER BY id_dzialki LIMIT ?",
        [*params, limit],
    )
    return [
        {
            "id": r["id_dzialki"],
            "numer": r["numer_dzialki"],
            "obreb": r["nazwa_obrebu"],
            "gmina": r["nazwa_gminy"],
            "jednostka": r["numer_jednostki"],
        }
        for r in rows
    ]


async def _timed(job, *args):
    started = time.perf_counter()
    try:
        return await asyncio.wait_for(asyncio.to_thread(job, *args), timeout=25)
    finally:
        record_timing("parcels_index", time.perf_counter() - started)


async def index_by_id(parcel_id: str) -> dict | None:
    return await _timed(_index_by_id, parcel_id)


async def index_by_point(lat: float, lon: float) -> dict | None:
    return await _timed(_index_by_point, lat, lon)


async def search(commune: str, region: str, number: str, limit: int) -> list[dict]:
    return await _timed(_search, commune, region, number, limit)


def index_source(row: dict) -> DataSource:
    path = Path(row["index_file"])
    stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    note = f"plik {path.name}, indeks z {stamp:%d.%m.%Y}"
    if row.get("index_data"):
        note += f", stan danych EGiB {row['index_data']}"
    return DataSource(
        name=INDEX_NAME,
        url=get_settings().parcels_parquet_url,
        license="Dane publiczne GUGiK, bezpłatne",
        retrieved_at=stamp,
        status=SourceStatus.ok,
        note=note,
    )
