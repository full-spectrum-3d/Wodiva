from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from app.core import cache as cache_module
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path):
    cache_module.set_cache(cache_module.Cache(tmp_path / "cache.sqlite"))
    yield
    cache_module.set_cache(None)


@pytest.fixture
def cube_path(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "cube.zarr"
    times = pd.date_range("2015-01-01", "2026-11-15", freq="D")
    lats = np.round(np.arange(51.0, 51.55, 0.1), 1)
    lons = np.round(np.arange(21.0, 21.55, 0.1), 1)
    rng = np.random.default_rng(1)
    shape = (len(times), len(lats), len(lons))
    doy = times.day_of_year.to_numpy()[:, None, None]
    season = np.sin(2 * np.pi * (doy - 105) / 365)
    tmax = 13 + 12 * season + rng.normal(0, 2, shape)
    ds = xr.Dataset(
        {
            "precip_mm": (("time", "latitude", "longitude"), np.where(rng.random(shape) < 0.4, 4.0, 0.0)),
            "tmax_c": (("time", "latitude", "longitude"), tmax),
            "tmin_c": (("time", "latitude", "longitude"), tmax - 8),
            "tdew_c": (("time", "latitude", "longitude"), tmax - 10),
            "wind10_ms": (("time", "latitude", "longitude"), np.full(shape, 3.0)),
            "rs_mj": (("time", "latitude", "longitude"), 10 + 8 * season + np.zeros(shape)),
            "pressure_kpa": (("time", "latitude", "longitude"), np.full(shape, 100.0)),
        },
        coords={"time": times, "latitude": lats, "longitude": lons},
    ).astype("float32")
    ds["precip_mm"][:, 0, 0] = np.nan
    ds.chunk({"time": 1024, "latitude": 8, "longitude": 8}).to_zarr(path, mode="w", consolidated=True)
    monkeypatch.setattr(get_settings(), "era5_cube_path", path)
    return path


@pytest.fixture
def analysis_day() -> date:
    return date(2024, 7, 15)


@pytest.fixture(autouse=True)
def offline_assistant(monkeypatch):
    from app.land.settings import land_settings

    monkeypatch.setattr(land_settings(), "ollama_url", "")
