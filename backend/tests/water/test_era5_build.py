import numpy as np
import pandas as pd
import pytest
import xarray as xr

from scripts.era5_common import chunks, daily_request, hourly_request, normalize, to_daily, write_cube

LAT = [51.2, 51.1, 51.0]
LON = [21.0, 21.1]


def _ds(var: str, times, value) -> xr.Dataset:
    data = np.full((len(times), len(LAT), len(LON)), value, dtype="float32")
    return xr.Dataset(
        {var: (("valid_time", "latitude", "longitude"), data)},
        coords={"valid_time": times, "latitude": LAT, "longitude": LON, "expver": "0001"},
    )


def _inputs(start="2024-07-01", days=5):
    daily_t = pd.date_range(start, periods=days, freq="D")
    hours = pd.date_range(start, periods=(days + 1) * 4, freq="6h")
    tmax = normalize(_ds("t2m", daily_t, 298.15))
    tmin = normalize(_ds("t2m", daily_t, 285.15))
    mean = normalize(xr.merge([_ds("d2m", daily_t, 283.15), _ds("sp", daily_t, 100500.0)]))
    accum = normalize(xr.merge([_ds("tp", hours, 0.004), _ds("ssrd", hours, 2.0e7)]))
    wind = normalize(xr.merge([_ds("u10", hours, 3.0), _ds("v10", hours, 4.0)]))
    return {"tmax": tmax, "tmin": tmin, "mean": mean}, accum, wind


def test_to_daily_units_and_accumulation_shift():
    daily, accum, wind = _inputs()
    ds = to_daily(daily, accum, wind)
    assert list(ds.latitude.values) == sorted(LAT)
    first = ds.isel(time=0, latitude=0, longitude=0)
    assert float(first.tmax_c) == pytest.approx(25.0)
    assert float(first.tmin_c) == pytest.approx(12.0)
    assert float(first.precip_mm) == pytest.approx(4.0)
    assert float(first.rs_mj) == pytest.approx(20.0)
    assert float(first.wind10_ms) == pytest.approx(5.0)
    assert float(first.pressure_kpa) == pytest.approx(100.5)
    assert pd.Timestamp(ds.time.values[0]) == pd.Timestamp("2024-07-01")


def test_write_and_append(tmp_path):
    out = tmp_path / "c.zarr"
    daily, accum, wind = _inputs("2024-07-01", 5)
    write_cube(to_daily(daily, accum, wind), out)
    daily, accum, wind = _inputs("2024-07-04", 6)
    write_cube(to_daily(daily, accum, wind), out, append=True)
    ds = xr.open_zarr(out)
    times = pd.to_datetime(ds.time.values)
    assert times.is_monotonic_increasing and times.is_unique
    assert times[-1] == pd.Timestamp("2024-07-09")


def test_requests_shape():
    c = chunks(pd.Timestamp("2024-11-01").date(), pd.Timestamp("2025-02-10").date())
    assert [x.tag for x in c] == ["2024_11-12", "2025_01-02"]
    r = daily_request(["2m_temperature"], "daily_maximum", c[0])
    assert r["daily_statistic"] == "daily_maximum" and r["month"] == ["11", "12"]
    h = hourly_request(["total_precipitation"], ["00:00"], c[1])
    assert h["data_format"] == "netcdf" and h["area"] == [55.1, 14.0, 49.0, 24.2]
