import asyncio
import csv
import io
import math
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache

import numpy as np
import pandas as pd

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.http import SourceError, fetch
from app.core.schemas import DataSource, SourceStatus, StationCheck

ARCHIVE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/dobowe/synop"
NOW_URL = "https://danepubliczne.imgw.pl/api/data/synop/id/{wmo}"
COL_YEAR, COL_MONTH, COL_DAY = 2, 3, 4
COL_TMAX, COL_TMAX_ST, COL_TMIN, COL_TMIN_ST, COL_TMEAN, COL_TMEAN_ST = 5, 6, 7, 8, 9, 10
COL_PRECIP, COL_PRECIP_ST = 13, 14


@dataclass(frozen=True)
class Station:
    code: str
    wmo: str
    name: str
    lat: float
    lon: float
    mountain: bool


def data_source(status: SourceStatus, note: str | None = None, start: date | None = None, end: date | None = None):
    return DataSource(
        name="IMGW-PIB – dane synoptyczne dobowe (archiwum) i bieżące",
        url="https://danepubliczne.imgw.pl/apiinfo",
        license="Dane publiczne IMGW-PIB; wymagane podanie źródła „Źródłem pochodzenia danych jest IMGW-PIB”",
        retrieved_at=datetime.now(UTC),
        period_start=start,
        period_end=end,
        status=status,
        note=note,
    )


@lru_cache
def stations() -> tuple[Station, ...]:
    path = get_settings().data_dir / "water" / "imgw_synop_stations.csv"
    with path.open(encoding="utf-8") as fh:
        return tuple(
            Station(r["code"], r["wmo"], r["name"], float(r["lat"]), float(r["lon"]), r["mountain"] == "1")
            for r in csv.DictReader(fh)
        )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def nearest(lat: float, lon: float) -> tuple[Station, float]:
    candidates = [s for s in stations() if not s.mountain]
    best = min(candidates, key=lambda s: haversine_km(lat, lon, s.lat, s.lon))
    return best, haversine_km(lat, lon, best.lat, best.lon)


def _value(row: list[str], col: int, status_col: int, zero_if_no_phenomenon: bool = False) -> float:
    status = row[status_col].strip() if len(row) > status_col else ""
    if status == "8":
        return np.nan
    if status == "9":
        return 0.0 if zero_if_no_phenomenon else np.nan
    try:
        return float(row[col].replace(",", "."))
    except (ValueError, IndexError):
        return np.nan


def parse_archive_zip(content: bytes, station_code: str) -> pd.DataFrame:
    records = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for name in zf.namelist():
            base = name.rsplit("/", 1)[-1].lower()
            if not base.startswith("s_d_") or base.startswith("s_d_t_"):
                continue
            text = zf.read(name).decode("cp1250", errors="replace")
            for row in csv.reader(io.StringIO(text)):
                if len(row) <= COL_PRECIP_ST or not row[0].strip().endswith(station_code):
                    continue
                try:
                    day = date(int(row[COL_YEAR]), int(row[COL_MONTH]), int(row[COL_DAY]))
                except ValueError:
                    continue
                records.append(
                    {
                        "date": day,
                        "tmax_c": _value(row, COL_TMAX, COL_TMAX_ST),
                        "tmin_c": _value(row, COL_TMIN, COL_TMIN_ST),
                        "tmean_c": _value(row, COL_TMEAN, COL_TMEAN_ST),
                        "precip_mm": _value(row, COL_PRECIP, COL_PRECIP_ST, zero_if_no_phenomenon=True),
                    }
                )
    if not records:
        return pd.DataFrame(columns=["tmax_c", "tmin_c", "tmean_c", "precip_mm"])
    return pd.DataFrame(records).drop_duplicates("date").set_index("date").sort_index()


def archive_files(station: Station, start: date, end: date) -> list[str]:
    files = []
    current_year = datetime.now(UTC).year
    today = datetime.now(UTC).date()
    for year in range(start.year, end.year + 1):
        if year >= current_year:
            last_month = min(end.month if year == end.year else 12, today.month - 1)
            first_month = start.month if year == start.year else 1
            files += [f"{year}/{year}_{m:02d}_s.zip" for m in range(first_month, last_month + 1)]
        else:
            files.append(f"{year}/{year}_{station.code}_s.zip")
    return files


_semaphore: asyncio.Semaphore | None = None


def _limit() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(3)
    return _semaphore


async def _archive_file(path: str, station: Station) -> list[dict]:
    cache = get_cache()
    missing_key = cache.key("imgw_missing", path)
    if cache.get(missing_key) is not None:
        return []

    async def run():
        async with _limit():
            response = await fetch("imgw", f"{ARCHIVE}/{path}", retries=0, timeout=8)
        frame = parse_archive_zip(response.content, station.code).reset_index()
        frame["date"] = frame["date"].astype(str)
        return frame.replace({np.nan: None}).to_dict(orient="records")

    try:
        return await cache.get_or_fetch("imgw_archive", (path, station.code), run) or []
    except SourceError as exc:
        if "404" in str(exc):
            cache.set(missing_key, True, "imgw_missing")
        return []


async def station_daily(station: Station, start: date, end: date) -> pd.DataFrame:
    parts = await asyncio.gather(*[_archive_file(p, station) for p in archive_files(station, start, end)])
    rows = [r for part in parts for r in part]
    if not rows:
        return pd.DataFrame(columns=["tmax_c", "tmin_c", "tmean_c", "precip_mm"])
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    frame = frame.drop_duplicates("date").set_index("date").sort_index().astype(float)
    return frame[(frame.index >= start) & (frame.index <= end)]


async def latest_observation(station: Station) -> dict | None:
    async def run():
        response = await fetch("imgw", NOW_URL.format(wmo=station.wmo), retries=1)
        return response.json()

    try:
        return await get_cache().get_or_fetch("imgw_now", (station.wmo,), run)
    except (SourceError, ValueError):
        return None


def compare(model: pd.DataFrame, obs: pd.DataFrame, station: Station, distance_km: float) -> StationCheck | None:
    joined = model[["precip_mm", "tmax_c", "tmin_c"]].join(
        obs[["precip_mm", "tmax_c", "tmin_c"]], lsuffix="_m", rsuffix="_s", how="inner"
    )
    joined = joined.dropna(subset=["precip_mm_m", "precip_mm_s"])
    if len(joined) < 20:
        return None
    pm = float(joined["precip_mm_m"].sum())
    ps = float(joined["precip_mm_s"].sum())
    tm = ((joined["tmax_c_m"] + joined["tmin_c_m"]) / 2 - (joined["tmax_c_s"] + joined["tmin_c_s"]) / 2).dropna()
    return StationCheck(
        station_code=station.wmo,
        station_name=station.name,
        distance_km=round(distance_km, 1),
        period_start=min(joined.index),
        period_end=max(joined.index),
        days_compared=len(joined),
        precip_model_mm=round(pm, 1),
        precip_station_mm=round(ps, 1),
        precip_diff_pct=round((pm - ps) / ps * 100, 1) if ps > 0 else None,
        tmean_bias_c=round(float(tm.mean()), 2) if len(tm) else None,
    )
