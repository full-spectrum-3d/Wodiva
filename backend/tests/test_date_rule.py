from datetime import date, timedelta

import httpx
import pytest
import respx

from app.core.dates import assert_not_after
from app.core.http import set_client
from app.core.validation import today_in_poland
from app.water import meteo
from app.water.sources import imgw, openmeteo


@pytest.fixture(autouse=True)
def fresh_client():
    set_client(None)
    yield
    set_client(None)


def _hourly(start: date, days: int) -> dict:
    times = [f"{start + timedelta(days=d)}T{h:02d}:00" for d in range(days) for h in range(24)]
    n = len(times)
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [15.0] * n,
            "dew_point_2m": [9.0] * n,
            "precipitation": [0.1] * n,
            "shortwave_radiation": [200.0] * n,
            "wind_speed_10m": [3.0] * n,
            "surface_pressure": [1005.0] * n,
        }
    }


@respx.mock
async def test_historical_analysis_has_no_future_data(cube_path, analysis_day):
    respx.get(url__startswith=imgw.ARCHIVE).mock(return_value=httpx.Response(404))
    result = await meteo.load(51.2, 21.2, analysis_day, 10)
    assert_not_after(result.series.days, analysis_day)
    assert max(result.frame.index) == analysis_day
    assert result.forecast.empty
    assert any(lim.code == "no_forecast" for lim in result.limitations)


@respx.mock
async def test_current_analysis_uses_openmeteo_for_gap_and_forecast(cube_path):
    today = today_in_poland()
    start = today - timedelta(days=openmeteo.PAST_DAYS)
    respx.get(openmeteo.FORECAST_URL).mock(
        return_value=httpx.Response(200, json=_hourly(start, openmeteo.PAST_DAYS + 8))
    )
    result = await meteo.load(51.2, 21.2, today, 10)
    assert_not_after(result.series.days, today)
    assert max(result.frame.index) == today
    assert len(result.forecast) == 7
    assert min(result.forecast.index) > today
    sources = {d.source for d in result.series.days}
    assert "openmeteo" in sources


@respx.mock
async def test_yesterday_gets_no_forecast_from_observed_days(cube_path):
    today = today_in_poland()
    yesterday = today - timedelta(days=1)
    start = today - timedelta(days=openmeteo.PAST_DAYS)
    respx.get(openmeteo.FORECAST_URL).mock(
        return_value=httpx.Response(200, json=_hourly(start, openmeteo.PAST_DAYS + 8))
    )
    result = await meteo.load(51.2, 21.2, yesterday, 10)
    assert_not_after(result.series.days, yesterday)
    assert result.forecast.empty
    assert any(lim.code == "no_forecast" for lim in result.limitations)


@respx.mock
async def test_no_cube_uses_archive(tmp_path, monkeypatch, analysis_day):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "era5_cube_path", tmp_path / "missing.zarr")
    start = meteo.history_start(analysis_day, 10)
    days = (analysis_day - start).days + 1
    respx.get(openmeteo.ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_hourly(start, days)))
    result = await meteo.load(51.2, 21.2, analysis_day, 10)
    assert max(result.frame.index) == analysis_day
    assert result.sources[0].status == "brak"


@respx.mock
async def test_early_date_does_not_invent_history(cube_path):
    respx.get(url__startswith=imgw.ARCHIVE).mock(return_value=httpx.Response(404))
    day = date(2016, 12, 1)
    result = await meteo.load(51.2, 21.2, day, 10)
    assert min(result.frame.index) == date(2015, 1, 1)
    assert not any(lim.code == "meteo_gaps" for lim in result.limitations)
