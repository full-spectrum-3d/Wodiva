import gc
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
HOURLY_DATASET = "reanalysis-era5-land"
SYNOPTIC = ["00:00", "06:00", "12:00", "18:00"]
THREE_HOURLY = [f"{h:02d}:00" for h in range(0, 24, 3)]
HOURLY_REQUESTS = {
    "accum": (["total_precipitation", "surface_solar_radiation_downwards"], ["00:00"]),
    "wind": (["10m_u_component_of_wind", "10m_v_component_of_wind"], SYNOPTIC),
    "temp": (["2m_temperature"], THREE_HOURLY),
    "humid": (["2m_dewpoint_temperature", "surface_pressure"], SYNOPTIC),
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


def _daily(arr: xr.DataArray, how: str) -> xr.DataArray:
    return getattr(arr.resample(time="1D"), how)()


def to_daily(accum: xr.Dataset, wind: xr.Dataset, temp: xr.Dataset, humid: xr.Dataset) -> xr.Dataset:
    t2m = _first(temp, ("t2m", "2m_temperature")) - 273.15
    tdew = _first(humid, ("d2m", "2m_dewpoint_temperature")) - 273.15
    sp = _first(humid, ("sp", "surface_pressure")) / 1000.0
    acc = accum.sel(time=accum["time"].dt.hour == 0)
    shifted_time = pd.to_datetime(acc["time"].values) - pd.Timedelta(days=1)
    tp = (_first(acc, ("tp", "total_precipitation")) * 1000.0).assign_coords(time=shifted_time)
    rs = (_first(acc, ("ssrd", "surface_solar_radiation_downwards")) / 1e6).assign_coords(time=shifted_time)
    speed = np.hypot(_first(wind, ("u10",)), _first(wind, ("v10",)))
    ds = xr.Dataset(
        {
            "precip_mm": tp.clip(min=0),
            "tmax_c": _daily(t2m, "max"),
            "tmin_c": _daily(t2m, "min"),
            "tdew_c": _daily(tdew, "mean"),
            "wind10_ms": _daily(speed, "mean"),
            "rs_mj": rs.clip(min=0),
            "pressure_kpa": _daily(sp, "mean"),
        }
    )
    ds = ds.dropna("time", how="all", subset=["tmax_c"])
    ds = ds.dropna("time", how="all", subset=["precip_mm"])
    return ds.astype("float32").sortby("time")


def _chunk_path(workdir: Path, name: str, chunk: Chunk) -> Path:
    return workdir / f"hourly_{name}_{chunk.tag}.nc"


def assemble_chunk(workdir: Path, chunk: Chunk, next_chunk: Chunk | None) -> xr.Dataset:
    parts = {name: open_any(_chunk_path(workdir, name, chunk)) for name in HOURLY_REQUESTS}
    accum = parts["accum"]
    extra = None
    if next_chunk is not None and _chunk_path(workdir, "accum", next_chunk).exists():
        extra = open_any(_chunk_path(workdir, "accum", next_chunk))
        accum = xr.concat([accum, extra.isel(time=[0])], dim="time").drop_duplicates("time")
    daily = to_daily(accum, parts["wind"], parts["temp"], parts["humid"]).load()
    for ds in [*parts.values(), extra]:
        if ds is not None:
            ds.close()
    log.info("złożono %s (%d dni)", chunk.tag, daily.sizes["time"])
    return daily


def assemble(workdir: Path, chunk_list: list[Chunk]) -> xr.Dataset:
    paths = []
    for i, chunk in enumerate(chunk_list):
        nxt = chunk_list[i + 1] if i + 1 < len(chunk_list) else None
        daily = assemble_chunk(workdir, chunk, nxt)
        path = workdir / f"day_{chunk.tag}.nc"
        daily.to_netcdf(path)
        daily.close()
        del daily
        gc.collect()
        paths.append(path)
    ds = xr.open_mfdataset(paths, combine="nested", concat_dim="time", chunks={"time": 366})
    return ds.drop_duplicates("time").sortby("time")


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
