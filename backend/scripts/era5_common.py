import logging
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

log = logging.getLogger("era5")

AREA = [55.1, 14.0, 49.0, 24.2]
DAILY_DATASET = "derived-era5-land-daily-statistics"
HOURLY_DATASET = "reanalysis-era5-land"
DAILY_REQUESTS = {
    "tmax": (["2m_temperature"], "daily_maximum"),
    "tmin": (["2m_temperature"], "daily_minimum"),
    "mean": (["2m_dewpoint_temperature", "surface_pressure"], "daily_mean"),
}
HOURLY_REQUESTS = {
    "accum": (["total_precipitation", "surface_solar_radiation_downwards"], ["00:00"]),
    "wind": (["10m_u_component_of_wind", "10m_v_component_of_wind"], ["00:00", "06:00", "12:00", "18:00"]),
}
CHUNKS = {"time": 1024, "latitude": 8, "longitude": 8}


@dataclass(frozen=True)
class Chunk:
    year: int
    months: tuple[int, ...]

    @property
    def tag(self) -> str:
        return f"{self.year}_{self.months[0]:02d}-{self.months[-1]:02d}"


def chunks(start: date, end: date, per: str = "year") -> list[Chunk]:
    out = []
    for year in range(start.year, end.year + 1):
        first = start.month if year == start.year else 1
        last = end.month if year == end.year else 12
        months = tuple(range(first, last + 1))
        if per == "month":
            out += [Chunk(year, (m,)) for m in months]
        else:
            out.append(Chunk(year, months))
    return out


def _days(chunk: Chunk) -> list[str]:
    return [f"{d:02d}" for d in range(1, 32)]


def daily_request(variables: list[str], statistic: str, chunk: Chunk) -> dict:
    return {
        "product_type": "reanalysis",
        "variable": variables,
        "year": str(chunk.year),
        "month": [f"{m:02d}" for m in chunk.months],
        "day": _days(chunk),
        "daily_statistic": statistic,
        "time_zone": "utc+00:00",
        "frequency": "1_hourly",
        "area": AREA,
    }


def hourly_request(variables: list[str], times: list[str], chunk: Chunk) -> dict:
    return {
        "variable": variables,
        "year": str(chunk.year),
        "month": [f"{m:02d}" for m in chunk.months],
        "day": _days(chunk),
        "time": times,
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": AREA,
    }


def jobs_for(chunk: Chunk, workdir: Path) -> list[tuple[str, dict, Path]]:
    jobs = []
    for name, (variables, stat) in DAILY_REQUESTS.items():
        jobs.append((DAILY_DATASET, daily_request(variables, stat, chunk), workdir / f"daily_{name}_{chunk.tag}.nc"))
    for name, (variables, times) in HOURLY_REQUESTS.items():
        jobs.append(
            (HOURLY_DATASET, hourly_request(variables, times, chunk), workdir / f"hourly_{name}_{chunk.tag}.nc")
        )
    return jobs


def download(jobs: list[tuple[str, dict, Path]], workers: int = 4) -> None:
    import cdsapi

    from app.core.config import get_settings

    settings = get_settings()
    if not settings.cdsapi_key and not Path.home().joinpath(".cdsapirc").exists():
        raise SystemExit("Brak klucza CDS: ustaw CDSAPI_KEY w .env albo utwórz ~/.cdsapirc")
    client = cdsapi.Client(url=settings.cdsapi_url, key=settings.cdsapi_key or None, quiet=True)
    todo = [j for j in jobs if not j[2].exists()]
    log.info("do pobrania: %d plików (pominięto %d gotowych)", len(todo), len(jobs) - len(todo))

    def run(job):
        dataset, request, target = job
        tmp = target.with_suffix(".part")
        log.info("CDS %s -> %s", dataset, target.name)
        client.retrieve(dataset, request, str(tmp))
        tmp.rename(target)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run, todo))


def open_any(path: Path) -> xr.Dataset:
    if zipfile.is_zipfile(path):
        out = path.with_suffix("")
        out.mkdir(exist_ok=True)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(out)
        parts = [xr.open_dataset(p) for p in sorted(out.glob("*.nc"))]
        ds = xr.merge(parts, compat="override")
    else:
        ds = xr.open_dataset(path)
    return normalize(ds)


def normalize(ds: xr.Dataset) -> xr.Dataset:
    rename = {k: "time" for k in ("valid_time", "date") if k in ds.dims or k in ds.coords}
    ds = ds.rename(rename)
    drop = [v for v in ("expver", "number", "step", "surface") if v in ds.coords or v in ds.variables]
    ds = ds.drop_vars(drop, errors="ignore")
    if "lat" in ds.dims:
        ds = ds.rename({"lat": "latitude", "lon": "longitude"})
    return ds.sortby("latitude").sortby("time")


def _first(ds: xr.Dataset, names: tuple[str, ...]) -> xr.DataArray:
    for n in names:
        if n in ds:
            return ds[n]
    raise KeyError(f"brak zmiennych {names} w {list(ds.data_vars)}")


def to_daily(daily: dict[str, xr.Dataset], accum: xr.Dataset, wind: xr.Dataset) -> xr.Dataset:
    tmax = _first(daily["tmax"], ("t2m", "2m_temperature")) - 273.15
    tmin = _first(daily["tmin"], ("t2m", "2m_temperature")) - 273.15
    tdew = _first(daily["mean"], ("d2m", "2m_dewpoint_temperature")) - 273.15
    sp = _first(daily["mean"], ("sp", "surface_pressure")) / 1000.0
    for arr in (tmax, tmin, tdew, sp):
        arr.coords["time"] = pd.to_datetime(arr["time"].values).normalize()
    acc = accum.sel(time=accum["time"].dt.hour == 0)
    shifted_time = pd.to_datetime(acc["time"].values) - pd.Timedelta(days=1)
    tp = (_first(acc, ("tp", "total_precipitation")) * 1000.0).assign_coords(time=shifted_time)
    rs = (_first(acc, ("ssrd", "surface_solar_radiation_downwards")) / 1e6).assign_coords(time=shifted_time)
    speed = np.hypot(_first(wind, ("u10",)), _first(wind, ("v10",)))
    wind10 = speed.resample(time="1D").mean()
    ds = xr.Dataset(
        {
            "precip_mm": tp.clip(min=0),
            "tmax_c": tmax,
            "tmin_c": tmin,
            "tdew_c": tdew,
            "wind10_ms": wind10,
            "rs_mj": rs.clip(min=0),
            "pressure_kpa": sp,
        }
    )
    ds = ds.dropna("time", how="all", subset=["tmax_c"])
    ds = ds.dropna("time", how="all", subset=["precip_mm"])
    return ds.astype("float32").sortby("time")


def assemble(workdir: Path, chunk_list: list[Chunk]) -> xr.Dataset:
    parts: dict[str, list[xr.Dataset]] = {k: [] for k in ("tmax", "tmin", "mean", "accum", "wind")}
    for chunk in chunk_list:
        for name in DAILY_REQUESTS:
            parts[name].append(open_any(workdir / f"daily_{name}_{chunk.tag}.nc"))
        for name in HOURLY_REQUESTS:
            parts[name].append(open_any(workdir / f"hourly_{name}_{chunk.tag}.nc"))
    joined = {k: xr.concat(v, dim="time").drop_duplicates("time") for k, v in parts.items()}
    return to_daily({k: joined[k] for k in DAILY_REQUESTS}, joined["accum"], joined["wind"])


def write_cube(ds: xr.Dataset, out: Path, append: bool = False) -> None:
    if append and out.exists():
        existing = xr.open_zarr(out)
        new = ds.sel(time=ds["time"] > existing["time"].values[-1])
        if new.sizes["time"] == 0:
            log.info("brak nowych dni")
            return
        ds = xr.concat([existing, new.astype("float32")], dim="time")
    ds = ds.chunk(CHUNKS)
    for v in ds.data_vars:
        ds[v].encoding = {}
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    ds.to_zarr(tmp, mode="w", consolidated=True)
    if out.exists():
        old = out.with_name(out.name + ".old")
        out.rename(old)
        tmp.rename(out)
        shutil.rmtree(old)
    else:
        tmp.rename(out)
    log.info("zapisano %s (%d dni)", out, ds.sizes["time"])


def last_day_available(lag_days: int) -> date:
    return date.today() - timedelta(days=lag_days)
