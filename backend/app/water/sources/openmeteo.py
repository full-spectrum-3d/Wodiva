from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.http import fetch
from app.core.schemas import DataSource, SourceStatus

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CUSTOMER_FORECAST_URL = "https://customer-api.open-meteo.com/v1/forecast"
CUSTOMER_ARCHIVE_URL = "https://customer-archive-api.open-meteo.com/v1/archive"
HOURLY = "temperature_2m,dew_point_2m,precipitation,shortwave_radiation,wind_speed_10m,surface_pressure"
PAST_DAYS = 31
FORECAST_DAYS = 8


def data_source(
    period_start: date | None, period_end: date | None, status: SourceStatus, note: str | None = None
) -> DataSource:
    return DataSource(
        name="Open-Meteo (ostatnie dni, prognoza 7 dni lub zapas archiwum)",
        url="https://open-meteo.com/en/terms",
        license="CC BY 4.0; API bezpłatne do użytku niekomercyjnego",
        retrieved_at=datetime.now(UTC),
        period_start=period_start,
        period_end=period_end,
        status=status,
        note=note,
    )


def cell_center(lat: float, lon: float) -> tuple[float, float]:
    return round(round(lat * 10) / 10, 1), round(round(lon * 10) / 10, 1)


def hourly_to_daily(payload: dict) -> pd.DataFrame:
    hourly = payload["hourly"]
    frame = pd.DataFrame(hourly)
    frame["time"] = pd.to_datetime(frame["time"])
    frame = frame.set_index("time").apply(pd.to_numeric, errors="coerce")
    grouped = frame.groupby(frame.index.date)
    counts = grouped["temperature_2m"].count()
    daily = pd.DataFrame(
        {
            "precip_mm": grouped["precipitation"].sum(min_count=20),
            "tmax_c": grouped["temperature_2m"].max(),
            "tmin_c": grouped["temperature_2m"].min(),
            "tdew_c": grouped["dew_point_2m"].mean(),
            "wind10_ms": grouped["wind_speed_10m"].mean(),
            "rs_mj": grouped["shortwave_radiation"].sum(min_count=20) * 3600 / 1e6,
            "pressure_kpa": grouped["surface_pressure"].mean() / 10,
        }
    )
    daily = daily[counts >= 20]
    daily.index.name = "date"
    return daily


def _params(lat: float, lon: float, **extra) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": HOURLY,
        "wind_speed_unit": "ms",
        "timezone": "GMT",
        **extra,
    }
    key = get_settings().openmeteo_api_key
    if key:
        params["apikey"] = key
    return params


def _frame_from_cache(rows: list[dict] | None) -> pd.DataFrame | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame.set_index("date").astype(float)


def _frame_to_cache(frame: pd.DataFrame) -> list[dict]:
    out = frame.reset_index()
    out["date"] = out["date"].astype(str)
    return out.replace({np.nan: None}).to_dict(orient="records")


async def recent_and_forecast(lat: float, lon: float) -> pd.DataFrame | None:
    clat, clon = cell_center(lat, lon)
    today = datetime.now(UTC).date()
    url = CUSTOMER_FORECAST_URL if get_settings().openmeteo_api_key else FORECAST_URL

    async def run():
        response = await fetch(
            "openmeteo", url, params=_params(clat, clon, past_days=PAST_DAYS, forecast_days=FORECAST_DAYS)
        )
        return _frame_to_cache(hourly_to_daily(response.json()))

    rows = await get_cache().get_or_fetch("openmeteo", (clat, clon, today.isoformat()), run)
    return _frame_from_cache(rows)


async def archive(lat: float, lon: float, start: date, end: date) -> pd.DataFrame | None:
    clat, clon = cell_center(lat, lon)
    end = min(end, datetime.now(UTC).date() - timedelta(days=2))
    url = CUSTOMER_ARCHIVE_URL if get_settings().openmeteo_api_key else ARCHIVE_URL

    async def run():
        response = await fetch(
            "openmeteo_archive",
            url,
            params=_params(clat, clon, start_date=start.isoformat(), end_date=end.isoformat()),
            retries=1,
        )
        return _frame_to_cache(hourly_to_daily(response.json()))

    rows = await get_cache().get_or_fetch("openmeteo_archive", (clat, clon, start.isoformat(), end.isoformat()), run)
    return _frame_from_cache(rows)
