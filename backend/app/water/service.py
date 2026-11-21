import asyncio
from dataclasses import dataclass, field
from datetime import date

from app.core.config import get_settings
from app.core.schemas import (
    DataSource,
    IrrigationAdvice,
    Limitation,
    Parcel,
    SoilInfo,
    StationCheck,
    WaterState,
)
from app.water import irrigation, meteo, soil
from app.water.engine.crops import Crop, get_crop, season_at
from app.water.engine.indices import climate_indicators
from app.water.engine.scenarios import run_scenarios
from app.water.engine.soil_water import Simulation, runoff_coefficient, simulate, state_at


@dataclass
class WaterPrep:
    parcel: Parcel
    analysis_date: date
    crop: Crop
    meteo: meteo.MeteoResult
    soil: SoilInfo
    station_check: StationCheck | None
    sources: list[DataSource] = field(default_factory=list)
    limitations: list[Limitation] = field(default_factory=list)


@dataclass
class WaterResult:
    state: WaterState
    irrigation: IrrigationAdvice
    soil: SoilInfo
    simulation: Simulation | None
    sources: list[DataSource]
    limitations: list[Limitation]


async def _meteo_with_station(lat: float, lon: float, day: date, years: int):
    result = await meteo.load(lat, lon, day, years)
    try:
        check, ds = await asyncio.wait_for(meteo.station_check(lat, lon, result.frame, day), timeout=15)
    except TimeoutError:
        check, ds = None, None
    return result, check, ds


async def prepare(parcel: Parcel, analysis_date: date, crop_code: str, soil_category: str | None = None) -> WaterPrep:
    crop = get_crop(crop_code)
    years = get_settings().analysis_years
    (met, check, station_ds), (soil_info, soil_sources, soil_limits) = await asyncio.gather(
        _meteo_with_station(parcel.centroid_lat, parcel.centroid_lon, analysis_date, years),
        soil.load(parcel.centroid_lat, parcel.centroid_lon, soil_category),
    )
    sources = [*met.sources, *([station_ds] if station_ds else []), *soil_sources]
    limitations = [*met.limitations, *soil_limits]
    met.series.station_check = check
    if check and check.precip_diff_pct is not None and abs(check.precip_diff_pct) > 25:
        limitations.append(
            Limitation(
                code="meteo_station_diff",
                message=f"Opad z modelu różni się o {check.precip_diff_pct:+.0f}% od stacji IMGW {check.station_name} "
                f"({check.distance_km:.0f} km) w ostatnich 12 miesiącach.",
                severity="ostrzeżenie",
                section="meteo",
            )
        )
    return WaterPrep(parcel, analysis_date, crop, met, soil_info, check, sources, limitations)


def compute(prep: WaterPrep, slope_pct: float | None = None, phase_offset_days: int | None = None) -> WaterResult:
    frame = prep.meteo.frame
    day = min(prep.analysis_date, max(frame.index))
    days = list(frame.index)
    precip = frame["precip_mm"].to_numpy(float)
    et0 = frame["et0_mm"].to_numpy(float)
    limitations = list(prep.limitations)
    category = prep.soil.iung_category
    coef = runoff_coefficient(slope_pct, category)
    if slope_pct is None:
        limitations.append(
            Limitation(
                code="slope_missing",
                message="Brak spadku terenu – spływ powierzchniowy liczony dla spadku 2%.",
                section="model wody",
            )
        )
    shift = None
    if phase_offset_days:
        season = season_at(prep.crop, day)
        if season is not None:
            shift = (season.year, int(phase_offset_days))
    sim = simulate(days, precip, et0, prep.crop, prep.soil.layers, coef, shift)
    years_cfg = get_settings().analysis_years
    years = [y for y in range(day.year - years_cfg, day.year + 1) if any(d.year == y for d in days)]
    if len(years) < years_cfg:
        limitations.append(
            Limitation(
                code="history_short",
                message=f"Historia meteo obejmuje {len(years)} lat ({years[0]}–{years[-1]}), mniej niż {years_cfg}.",
                severity="ostrzeżenie",
                section="ocena historyczna",
            )
        )
    sw_state = state_at(sim, day, years_cfg)
    climate = climate_indicators(frame, day, prep.crop, category, years, sim)
    scenarios = run_scenarios(sim, precip, et0, prep.crop, prep.soil.layers, coef, day, shift)
    if prep.crop.kbw_group is None:
        limitations.append(
            Limitation(
                code="kbw_no_threshold",
                message=f"Dla uprawy „{prep.crop.name}” rozporządzenie nie podaje progu KBW – ocena suszy "
                "opiera się na modelu wody w glebie.",
                section="ocena",
            )
        )
    advice = irrigation.advise(sim, prep.crop, prep.parcel, day, prep.meteo.forecast)
    state = WaterState(
        analysis_date=prep.analysis_date,
        crop=prep.crop.code,
        crop_name=prep.crop.name,
        meteo_until=max(frame.index),
        era5_until=prep.meteo.series.era5_until,
        climate=climate,
        soil_water=sw_state,
        scenarios=scenarios,
        station_check=prep.station_check,
        meteo_last_90=prep.meteo.series.days,
        forecast=prep.meteo.series.forecast,
    )
    return WaterResult(state, advice, prep.soil, sim, list(prep.sources), limitations)
