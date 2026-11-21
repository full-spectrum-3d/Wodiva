import numpy as np
import pandas as pd
import pytest
import xarray as xr

from scripts.era5_common import chunks, hourly_request, jobs_for, normalize, to_daily, write_cube

LAT = [51.2, 51.1, 51.0]
LON = [21.0, 21.1]


def _ds(var: str, times, values) -> xr.Dataset:
    data = np.broadcast_to(np.asarray(values, dtype="float32")[:, None, None], (len(times), len(LAT), len(LON)))
    return xr.Dataset(
        {var: (("valid_time", "latitude", "longitude"), data.copy())},
        coords={"valid_time": times, "latitude": LAT, "longitude": LON, "expver": "0001"},
    )


def _merge(*parts):
    return normalize(xr.merge(parts, compat="override"))


def _inputs(start="2024-07-01", days=5):
    t3 = pd.date_range(start, periods=days * 8, freq="3h")
    t6 = pd.date_range(start, periods=(days + 1) * 4, freq="6h")
    temp_k = 285.15 + 13.0 * (t3.hour.to_numpy() == 12)
    temp = _merge(_ds("t2m", t3, temp_k))
    humid = _merge(_ds("d2m", t6, np.full(len(t6), 283.15)), _ds("sp", t6, np.full(len(t6), 100500.0)))
    accum = _merge(_ds("tp", t6, np.full(len(t6), 0.004)), _ds("ssrd", t6, np.full(len(t6), 2.0e7)))
    wind = _merge(_ds("u10", t6, np.full(len(t6), 3.0)), _ds("v10", t6, np.full(len(t6), 4.0)))
    return accum, wind, temp, humid


def test_to_daily_units_and_accumulation_shift():
    ds = to_daily(*_inputs())
    assert list(ds.latitude.values) == sorted(LAT)
    first = ds.isel(time=0, latitude=0, longitude=0)
    assert float(first.tmax_c) == pytest.approx(25.0)
    assert float(first.tmin_c) == pytest.approx(12.0)
    assert float(first.tdew_c) == pytest.approx(10.0)
    assert float(first.precip_mm) == pytest.approx(4.0)
    assert float(first.rs_mj) == pytest.approx(20.0)
    assert float(first.wind10_ms) == pytest.approx(5.0)
    assert float(first.pressure_kpa) == pytest.approx(100.5)
    assert pd.Timestamp(ds.time.values[0]) == pd.Timestamp("2024-07-01")


def test_write_and_append(tmp_path):
    out = tmp_path / "c.zarr"
    write_cube(to_daily(*_inputs("2024-07-01", 5)), out)
    write_cube(to_daily(*_inputs("2024-07-04", 6)), out, append=True)
    times = pd.to_datetime(xr.open_zarr(out).time.values)
    assert times.is_monotonic_increasing and times.is_unique
    assert times[-1] == pd.Timestamp("2024-07-09")


def test_requests_shape(tmp_path):
    c = chunks(pd.Timestamp("2024-11-01").date(), pd.Timestamp("2025-02-10").date())
    assert [x.tag for x in c] == ["2024_11-12", "2025_01-02"]
    h = hourly_request(["total_precipitation"], ["00:00"], c[1])
    assert h["data_format"] == "netcdf" and h["area"] == [55.1, 14.0, 49.0, 24.2]
    jobs = jobs_for(c[0], tmp_path)
    assert {j[0] for j in jobs} == {"reanalysis-era5-land"}
    assert {j[2].name for j in jobs} == {f"hourly_{n}_2024_11-12.nc" for n in ("accum", "wind", "temp", "humid")}
