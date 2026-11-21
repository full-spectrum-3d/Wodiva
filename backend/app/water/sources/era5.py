import threading
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from app.core.config import get_settings
from app.core.schemas import DataSource, SourceStatus

VARIABLES = ["precip_mm", "tmax_c", "tmin_c", "tdew_c", "wind10_ms", "rs_mj", "pressure_kpa"]
GRID_STEP = 0.1
_lock = threading.Lock()


def cell_id(lat: float, lon: float) -> str:
    return f"{round(lat / GRID_STEP) * GRID_STEP:.1f}_{round(lon / GRID_STEP) * GRID_STEP:.1f}"


def data_source(
    period_start: date | None, period_end: date | None, status: SourceStatus, note: str | None = None
) -> DataSource:
    updated = None
    path = get_settings().era5_cube_path
    if path.exists():
        updated = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return DataSource(
        name="ERA5-Land (Copernicus C3S) – kostka dzienna dla Polski, 0,1°",
        url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land",
        license="Licence to use Copernicus Products (bezpłatna, wymaga podania źródła)",
        retrieved_at=updated or datetime.now(UTC),
        period_start=period_start,
        period_end=period_end,
        status=status,
        note=note or (f"ostatnia aktualizacja kostki: {updated:%Y-%m-%d}" if updated else None),
    )


@lru_cache
def _open(path: str, mtime: float) -> xr.Dataset:
    return xr.open_zarr(path, consolidated=True)


def open_cube(path: Path | None = None) -> xr.Dataset | None:
    path = path or get_settings().era5_cube_path
    if not path.exists():
        return None
    return _open(str(path), path.stat().st_mtime)


def cube_end(ds: xr.Dataset) -> date:
    return pd.Timestamp(ds["time"].values[-1]).date()


def _neighbour_weights(ds: xr.Dataset, lat: float, lon: float):
    lats = ds["latitude"].values
    lons = ds["longitude"].values
    i = int(np.clip(np.searchsorted(lats, lat) - 1, 0, len(lats) - 2))
    j = int(np.clip(np.searchsorted(lons, lon) - 1, 0, len(lons) - 2))
    fy = float(np.clip((lat - lats[i]) / (lats[i + 1] - lats[i]), 0, 1))
    fx = float(np.clip((lon - lons[j]) / (lons[j + 1] - lons[j]), 0, 1))
    cells = [
        (i, j, (1 - fy) * (1 - fx)),
        (i, j + 1, (1 - fy) * fx),
        (i + 1, j, fy * (1 - fx)),
        (i + 1, j + 1, fy * fx),
    ]
    return i, j, cells


def point_series(lat: float, lon: float, start: date, end: date, ds: xr.Dataset | None = None) -> pd.DataFrame | None:
    ds = ds if ds is not None else open_cube()
    if ds is None:
        return None
    end = min(end, cube_end(ds))
    if end < start:
        return None
    i, j, cells = _neighbour_weights(ds, lat, lon)
    window = (
        ds[VARIABLES]
        .isel(latitude=slice(max(i - 1, 0), i + 3), longitude=slice(max(j - 1, 0), j + 3))
        .sel(time=slice(str(start), str(end)))
    )
    with _lock:
        block = {v: window[v].values for v in VARIABLES}
    oi, oj = max(i - 1, 0), max(j - 1, 0)
    out = {}
    for v in VARIABLES:
        arr = block[v]
        stack = np.stack([arr[:, ci - oi, cj - oj] for ci, cj, _ in cells], axis=1)
        w = np.array([c[2] for c in cells])
        valid = ~np.isnan(stack)
        wsum = (valid * w).sum(axis=1)
        if np.all(wsum == 0):
            flat = arr.reshape(arr.shape[0], -1)
            good = ~np.all(np.isnan(flat), axis=0)
            out[v] = flat[:, np.argmax(good)] if good.any() else np.full(arr.shape[0], np.nan)
            continue
        out[v] = np.where(wsum > 0, np.nansum(stack * w, axis=1) / np.where(wsum > 0, wsum, 1), np.nan)
    frame = pd.DataFrame(out, index=pd.to_datetime(window["time"].values).date)
    frame.index.name = "date"
    return frame[frame.index <= end]
