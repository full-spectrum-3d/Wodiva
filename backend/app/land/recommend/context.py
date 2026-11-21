from datetime import date
from typing import Any

from app.core.schemas import IrrigationAdvice, ScenarioResult, SoilInfo, WaterState
from app.land.engine import phenology
from app.land.models import Cause, LandResult, Level
from app.land.recommend.rules import months_label

RISK_FREQ = 0.5


def scenario_text(scenarios: list[ScenarioResult], code: str) -> str:
    for s in scenarios:
        if s.code == code:
            if s.stress_days_saved <= 0:
                return (
                    f" Symulacja dla tej działki: w roku {s.reference_year} ({s.name.lower()}) nie zmieniłoby "
                    "to liczby dni stresu wodnego."
                )
            return (
                f" Symulacja dla tej działki: w roku {s.reference_year} ({s.name.lower()}) byłoby ok. "
                f"{s.stress_days_saved} dni stresu wodnego mniej "
                f"({s.stress_days_scenario} zamiast {s.stress_days_baseline})."
            )
    return ""


def risk_months(water: WaterState) -> list[int]:
    months = set()
    for d in water.climate.risk_calendar:
        if (d.stress_freq or 0) >= RISK_FREQ or (d.kbw_deficit_freq or 0) >= RISK_FREQ:
            months.add(d.month)
    return sorted(months)


def _where(distance_m: float | None) -> str | None:
    if distance_m is None:
        return None
    if distance_m <= 5:
        return "na działce lub przy jej granicy"
    return f"ok. {distance_m:.0f} m od działki"


def build(
    crop: str,
    day: date,
    is_agricultural: bool | None,
    area_ha: float,
    water: WaterState,
    soil: SoilInfo | None,
    irrigation: IrrigationAdvice | None,
    land: LandResult,
    causes: list[Cause],
    risk_level: Level | None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "crop": crop,
        "phase": phenology.phase_on(crop, day),
        "month": day.month,
        "risk_level": risk_level.value if risk_level else None,
        "non_agricultural": is_agricultural is False,
        "area_ha": area_ha,
        "irrigation_status": irrigation.status if irrigation else None,
    }
    for cause in causes:
        ctx[f"cause_{cause.key}"] = cause.active
    c = water.climate
    ctx["risk_months_label"] = months_label(risk_months(water))
    ctx["deficit_seasons"] = len(c.seasons_with_kbw_drought)
    ctx["seasons_analyzed"] = len(c.years_analyzed)
    if c.years_analyzed:
        ctx["deficit_share"] = len(c.seasons_with_kbw_drought) / len(c.years_analyzed)
    if soil is not None:
        ctx["awc_mm"] = soil.awc_mm_100cm
        ctx["sand_pct"] = soil.layers[0].sand_pct if soil.layers else None
    t = land.terrain
    if t is not None and t.runoff_risk is not None:
        ctx["dem_source"] = t.dem_source
        ctx["runoff_risk"] = t.runoff_risk.value
        ctx["mean_slope_pct"] = t.mean_slope_pct
        ctx["flow_path_length_m"] = t.flow_path_length_m
        ctx["channel_in_parcel"] = t.flow_path_length_m > 0
        depressions = [
            f for f in t.features if f.kind == "zagłębienie" and f.properties.get("inside_parcel_share", 0) >= 0.5
        ]
        ctx["depressions_in_parcel"] = len(depressions)
        if depressions:
            top = max(depressions, key=lambda f: f.properties["volume_m3"])
            ctx["largest_depression_area_m2"] = top.properties["area_m2"]
            ctx["largest_depression_depth_m"] = top.properties["max_depth_m"]
            ctx["largest_depression_volume_m3"] = top.properties["volume_m3"]
        channels = [f for f in t.features if f.kind == "linia spływu"]
        if channels:
            ctx["channel_area_ha"] = max(f.properties["max_contributing_area_ha"] for f in channels)
    h = land.hydro
    if h is not None and h.status.value != "brak":
        ctx["ditch_where"] = _where(h.ditch_distance_m)
        ctx["watercourse_where"] = _where(h.watercourse_distance_m)
        ctx["wetland_where"] = _where(h.wetland_distance_m)
        ctx["ditch_distance_m"] = h.ditch_distance_m
        ctx["watercourse_distance_m"] = h.watercourse_distance_m
        ctx["wetland_distance_m"] = h.wetland_distance_m
        ctx["tree_cover_pct"] = h.tree_cover_pct_500m
        ctx["water_area_ha"] = h.water_area_ha_500m
        ctx["wetland_area_ha"] = h.wetland_area_ha_500m
    ctx["scenario_mulch"] = scenario_text(water.scenarios, "mulcz")
    ctx["scenario_organic"] = scenario_text(water.scenarios, "prochnica")
    ctx["scenario_runoff"] = scenario_text(water.scenarios, "splyw")
    return ctx
