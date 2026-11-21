import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.core.http import SourceError
from app.core.schemas import DataSource, Limitation, MeteoDay, MeteoSeries, SourceStatus, StationCheck
from app.core.validation import today_in_poland
from app.water.engine.et0 import et0_for_days
from app.water.sources import era5, imgw, openmeteo

log = logging.getLogger("wodiva.meteo")

COLUMNS = ["precip_mm", "tmax_c", "tmin_c", "tdew_c", "wind10_ms", "rs_mj", "pressure_kpa"]


@dataclass
class MeteoResult:
    frame: pd.DataFrame
    forecast: pd.DataFrame
    series: MeteoSeries
    sources: list[DataSource] = field(default_factory=list)
    limitations: list[Limitation] = field(default_factory=list)


def history_start(analysis_date: date, years: int) -> date:
    return date(analysis_date.year - years - 1, 1, 1)


def with_et0(frame: pd.DataFrame, lat: float) -> pd.DataFrame:
    if frame.empty:
        frame["et0_mm"] = []
        return frame
    frame = frame.copy()
    frame["et0_mm"] = et0_for_days(
        list(frame.index),
        frame["tmax_c"].to_numpy(float),
        frame["tmin_c"].to_numpy(float),
        frame["rs_mj"].to_numpy(float),
        frame["wind10_ms"].to_numpy(float),
        frame["tdew_c"].to_numpy(float),
        frame["pressure_kpa"].to_numpy(float),
        lat,
    )
    return frame


def fill_gaps(frame: pd.DataFrame, start: date, end: date) -> tuple[pd.DataFrame, int]:
    index = pd.Index([d.date() for d in pd.date_range(start, end, freq="D")], name="date")
    full = frame.reindex(index)
    # dzień z luką w dowolnej kolumnie (nie tylko tmax): NaN w opadzie czy promieniowaniu psuje cały bilans wody
    missing = int(full[COLUMNS].isna().any(axis=1).sum())
    if missing:
        doy = pd.Series([d.timetuple().tm_yday for d in index], index=index)
        for col in COLUMNS:
            if col == "precip_mm":
                full[col] = full[col].fillna(0.0)
                continue
            clim = full[col].groupby(doy).transform("mean")
            full[col] = full[col].fillna(clim).interpolate(limit_direction="both")
    return full, missing


def _to_days(frame: pd.DataFrame, source_col: pd.Series) -> list[MeteoDay]:
    out = []
    for day, row in frame.iterrows():
        values = {k: (None if pd.isna(row.get(k)) else round(float(row[k]), 2)) for k in [*COLUMNS, "et0_mm"]}
        out.append(MeteoDay(date=day, source=source_col.get(day, "era5"), **values))
    return out


async def load(lat: float, lon: float, analysis_date: date, years: int) -> MeteoResult:
    start = history_start(analysis_date, years)
    today = today_in_poland()  # ta sama strefa co walidacja daty, inaczej po północy prognoza wchodzi jako obserwacja
    sources: list[DataSource] = []
    limitations: list[Limitation] = []
    parts: list[pd.DataFrame] = []
    origin: dict[date, str] = {}

    cube = await asyncio.to_thread(era5.point_series, lat, lon, start, analysis_date)
    era5_until = None
    if cube is not None and not cube.empty:
        era5_until = max(cube.index)
        parts.append(cube)
        origin.update({d: "era5" for d in cube.index})
        sources.append(era5.data_source(min(cube.index), era5_until, SourceStatus.ok))
    else:
        sources.append(era5.data_source(None, None, SourceStatus.missing, "kostka ERA5 niedostępna na serwerze"))

    need_from = (era5_until + timedelta(days=1)) if era5_until else start
    # tylko dziś: dla wczoraj dni „prognozy” byłyby już obserwacjami po dacie analizy
    is_current = analysis_date >= today
    forecast = pd.DataFrame(columns=COLUMNS)
    use_recent = is_current or (need_from <= analysis_date and (today - need_from).days <= openmeteo.PAST_DAYS)

    if need_from <= analysis_date and (today - need_from).days > openmeteo.PAST_DAYS:
        arch_end = analysis_date if not is_current else today - timedelta(days=openmeteo.PAST_DAYS - 1)
        try:
            arch = await openmeteo.archive(lat, lon, need_from, arch_end)
        except SourceError as exc:
            arch = None
            sources.append(openmeteo.data_source(need_from, arch_end, SourceStatus.missing, str(exc)))
        if arch is not None and not arch.empty:
            parts.append(arch)
            origin.update({d: "openmeteo" for d in arch.index if d not in origin})
            sources.append(
                openmeteo.data_source(min(arch.index), max(arch.index), SourceStatus.ok, "archiwum (zapas za kostkę)")
            )

    if use_recent:
        try:
            recent = await openmeteo.recent_and_forecast(lat, lon)
        except SourceError as exc:
            recent = None
            sources.append(openmeteo.data_source(need_from, analysis_date, SourceStatus.missing, str(exc)))
        if recent is not None:
            past = recent[(recent.index >= need_from) & (recent.index <= analysis_date)]
            parts.append(past)
            origin.update({d: "openmeteo" for d in past.index if d not in origin})
            if is_current:
                forecast = recent[recent.index > analysis_date].head(7)
            sources.append(
                openmeteo.data_source(
                    min(past.index) if len(past) else None,
                    max(forecast.index) if len(forecast) else analysis_date,
                    SourceStatus.ok,
                    "ostatnie dni i prognoza 7 dni, cache na komórkę 0,1°" if is_current else "ostatnie dni",
                )
            )

    if not parts:
        raise SourceError("meteo", "brak danych meteorologicznych (ERA5 i Open-Meteo niedostępne)")

    merged = pd.concat(parts)
    merged = merged[~merged.index.duplicated(keep="first")].sort_index()
    merged = merged[(merged.index >= start) & (merged.index <= analysis_date)]
    if merged.empty:
        raise SourceError("meteo", "brak danych meteorologicznych do daty analizy")
    meteo_until = max(merged.index)
    full, missing = fill_gaps(merged[COLUMNS], min(merged.index), meteo_until)
    if meteo_until < analysis_date:
        limitations.append(
            Limitation(
                code="meteo_lag",
                message=f"Dane meteo kończą się {meteo_until:%d.%m.%Y}, czyli przed datą analizy.",
                severity="ostrzeżenie",
                section="meteo",
            )
        )
    if missing > 0:
        limitations.append(
            Limitation(
                code="meteo_gaps",
                message=f"Uzupełniono {missing} brakujących dni meteo wartościami klimatologicznymi (opad = 0).",
                severity="info" if missing < 30 else "ostrzeżenie",
                section="meteo",
            )
        )
    if not is_current:
        limitations.append(
            Limitation(
                code="no_forecast",
                message="Data historyczna – nie użyto prognozy pogody ani danych późniejszych niż data analizy.",
                section="nawadnianie",
            )
        )
    full = with_et0(full, lat)
    forecast = with_et0(forecast[COLUMNS].astype(float), lat) if len(forecast) else forecast
    origin_series = pd.Series(origin)
    series = MeteoSeries(
        lat=lat,
        lon=lon,
        cell_id=era5.cell_id(lat, lon),
        days=_to_days(full.tail(90), origin_series),
        forecast=[d.model_copy(update={"source": "prognoza"}) for d in _to_days(forecast, origin_series)],
        era5_until=era5_until,
    )
    return MeteoResult(frame=full, forecast=forecast, series=series, sources=sources, limitations=limitations)


async def station_check(
    lat: float, lon: float, model: pd.DataFrame, analysis_date: date
) -> tuple[StationCheck | None, DataSource]:
    station, distance = imgw.nearest(lat, lon)
    start = max(analysis_date - timedelta(days=365), min(model.index))
    obs, latest = await asyncio.gather(
        imgw.station_daily(station, start, analysis_date),
        imgw.latest_observation(station) if analysis_date >= today_in_poland() else _none(),
    )
    window = model[(model.index >= start) & (model.index <= analysis_date)]
    check = imgw.compare(window, obs, station, distance) if len(obs) else None
    if check is not None and latest:
        check.latest_obs = {k: latest.get(k) for k in ("data_pomiaru", "godzina_pomiaru", "temperatura", "suma_opadu")}
    status = SourceStatus.ok if check else SourceStatus.missing
    note = f"stacja {station.name} ({distance:.0f} km)" + ("" if check else " – brak danych archiwalnych")
    return check, imgw.data_source(status, note, start, analysis_date)


async def _none():
    return None


def summary_frame(frame: pd.DataFrame) -> dict:
    return {
        "days": len(frame),
        "precip_total_mm": float(np.nansum(frame["precip_mm"])),
        "et0_total_mm": float(np.nansum(frame["et0_mm"])),
    }
