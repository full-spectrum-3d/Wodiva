from collections import OrderedDict
from datetime import date

from app.core.contracts import LandInterpretation, LandObservation
from app.core.schemas import Cause as CoreCause
from app.core.schemas import Confidence as CoreConfidence
from app.core.schemas import HydroInfo as CoreHydro
from app.core.schemas import IrrigationAdvice, Parcel, SoilInfo, WaterState
from app.core.schemas import Recommendation as CoreRecommendation
from app.core.schemas import SatelliteState as CoreSatellite
from app.core.schemas import TerrainInfo as CoreTerrain
from app.land import catalog, causes, collect, confidence
from app.land.assessment import assess
from app.land.models import (
    DroughtContext,
    HydroInfo,
    LandResult,
    RadarState,
    SatelliteState,
    TerrainInfo,
)
from app.land.recommend import agro, context, retention
from app.land.sources import pigpib

CAUSE_CODES = {"opad": "opad", "parowanie": "upał", "gleba": "gleba", "splyw": "spływ", "krajobraz": "retencja"}
PHASE_NAMES = {
    "vegetative": "rozwój",
    "peak": "pełnia",
    "ripening": "dojrzewanie",
    "emergence": "wschody",
    "after_harvest": "po zbiorze",
    "before_sowing": "przed siewem",
    "dormancy": "spoczynek zimowy",
}
ARTIFACTS_LIMIT = 32
_artifacts: OrderedDict[tuple[str, date], collect.LandArtifacts] = OrderedDict()


def artifacts_for(parcel_id: str, day: date) -> collect.LandArtifacts | None:
    return _artifacts.get((parcel_id, day))


def _remember(parcel_id: str, day: date, artifacts: collect.LandArtifacts) -> None:
    _artifacts[(parcel_id, day)] = artifacts
    _artifacts.move_to_end((parcel_id, day))
    while len(_artifacts) > ARTIFACTS_LIMIT:
        _artifacts.popitem(last=False)


def to_core_satellite(sat: SatelliteState, radar: RadarState | None) -> CoreSatellite:
    latest = sat.latest
    vci_values = [v for v in (sat.vci_ndvi, sat.vci_ndmi) if v is not None]
    return CoreSatellite(
        scenes_used=(1 if latest else 0) + len(sat.history) + sat.season_points,
        last_scene_date=latest.date if latest else None,
        ndvi=latest.ndvi if latest else None,
        ndmi=latest.ndmi if latest else None,
        vci=round(100 * min(vci_values), 0) if vci_values else None,
        crop_phase=PHASE_NAMES.get(sat.phase, sat.phase),
        phase_offset_days=sat.phase_offset_days,
        surface_state=sat.surface_state
        if sat.surface_state in ("roślinność", "goła gleba", "po zbiorze")
        else "nieznany",
        s1_anomaly_db=radar.vh_vv_anomaly_db
        if radar and sat.interpretable
        else (radar.vv_anomaly_db if radar else None),
        details={"sentinel": sat.model_dump(mode="json"), "radar": radar.model_dump(mode="json") if radar else None},
    )


def to_core_terrain(terrain: TerrainInfo, hydro: HydroInfo | None) -> CoreTerrain:
    def features(kind: str) -> list[dict]:
        return [{"geometry": f.geometry, **f.properties} for f in terrain.features if f.kind == kind]

    return CoreTerrain(
        slope_mean_pct=terrain.mean_slope_pct,
        slope_max_pct=terrain.max_slope_pct,
        twi_mean=terrain.twi_mean,
        depressions=features("zagłębienie"),
        flow_lines=features("linia spływu"),
        tree_cover_buffer_pct=hydro.tree_cover_pct_500m if hydro else None,
        details={"terrain": terrain.model_dump(mode="json")},
    )


def to_core_hydro(hydro: HydroInfo, drought: DroughtContext | None) -> CoreHydro:
    by_group: dict[str, list[dict]] = {}
    for item in hydro.features:
        by_group.setdefault(item["group"], []).append({k: v for k, v in item.items() if k != "group"})

    def items(group: str, distance: float | None, **extra) -> list[dict]:
        if distance is None:
            return []
        found = by_group.get(group) or [{"distance_m": distance, "source": "BDOT10k"}]
        return [{**f, **extra} for f in found]

    return CoreHydro(
        watercourses=items("watercourse", hydro.watercourse_distance_m, in_parcel=hydro.watercourse_in_parcel),
        water_bodies=items("water", hydro.water_body_distance_m, area_ha_500m=hydro.water_area_ha_500m),
        ditches=items("ditch", hydro.ditch_distance_m, in_parcel=hydro.ditch_in_parcel),
        wetlands=[]
        if hydro.wetland_distance_m is None
        else [
            {"distance_m": hydro.wetland_distance_m, "area_ha_500m": hydro.wetland_area_ha_500m, "source": "BDOT10k"}
        ],
        groundwater=hydro.groundwater,
        edo=drought.model_dump(mode="json") if drought else None,
        details={"hydro": hydro.model_dump(mode="json")},
    )


def to_core(result: LandResult) -> LandObservation:
    return LandObservation(
        satellite=to_core_satellite(result.satellite, result.radar) if result.satellite else None,
        terrain=to_core_terrain(result.terrain, result.hydro)
        if result.terrain and result.terrain.runoff_risk is not None
        else None,
        hydro=to_core_hydro(result.hydro, result.drought) if result.hydro else None,
        sources=[catalog.to_source(n) for n in result.sources],
        limitations=[catalog.to_limitation(n) for n in result.notes],
    )


def from_core(land: LandObservation) -> LandResult:
    result = LandResult()
    if land.satellite is not None:
        if land.satellite.details.get("sentinel"):
            result.satellite = SatelliteState.model_validate(land.satellite.details["sentinel"])
        if land.satellite.details.get("radar"):
            result.radar = RadarState.model_validate(land.satellite.details["radar"])
    if land.terrain is not None and land.terrain.details.get("terrain"):
        result.terrain = TerrainInfo.model_validate(land.terrain.details["terrain"])
    if land.hydro is not None:
        if land.hydro.details.get("hydro"):
            result.hydro = HydroInfo.model_validate(land.hydro.details["hydro"])
        if land.hydro.edo:
            result.drought = DroughtContext.model_validate(land.hydro.edo)
    return result


async def observe(parcel: Parcel, analysis_date: date, crop: str) -> LandObservation:
    result, artifacts = await collect.collect(
        parcel.geometry_wkt_2180,
        parcel.area_ha,
        parcel.size_class == "mała",
        parcel.centroid_lon,
        parcel.centroid_lat,
        crop,
        analysis_date,
    )
    _remember(parcel.id, analysis_date, artifacts)
    observation = to_core(result)
    if observation.satellite is not None:
        observation.satellite.details["timings_s"] = result.timings_s
    return observation


def _recommendation(rec) -> CoreRecommendation:
    location = (
        {
            "type": "Feature",
            "geometry": rec.location.geometry,
            "properties": {"kind": rec.location.kind, **rec.location.properties},
        }
        if rec.location
        else None
    )
    return CoreRecommendation(
        category=rec.category,
        title=rec.title,
        justification=f"{rec.action} Dlaczego: {rec.rationale}",
        evidence_ids=rec.evidence,
        eco_scheme=rec.ecoscheme,
        priority=rec.priority,
        location=location,
    )


def irrigation_recommendation(
    irrigation: IrrigationAdvice | None, groundwater: dict | None = None
) -> CoreRecommendation | None:
    if irrigation is None or irrigation.status in ("nie dotyczy", "niezalecane"):
        return None
    title = "Nawadnianie zalecane" if irrigation.status == "zalecane" else "Monitoruj potrzebę nawadniania"
    parts = [irrigation.reason]
    if irrigation.first_day:
        parts.append(f"Termin: od {irrigation.first_day.isoformat()}.")
    if irrigation.gross_dose_mm:
        parts.append(
            f"Dawka brutto ok. {irrigation.gross_dose_mm:.0f} mm"
            + (f" w {irrigation.split_into} dawkach." if irrigation.split_into and irrigation.split_into > 1 else ".")
        )
    if irrigation.volume_m3:
        parts.append(f"Objętość wody ok. {irrigation.volume_m3:.0f} m³ na działkę.")
    if pigpib.is_quantity_poor(groundwater):
        parts.append(
            "Wody podziemne w tym rejonie mają słaby stan ilościowy lub są zagrożone (PIG-PIB): "
            "ogranicz pobór z ujęć głębinowych, korzystaj najpierw z retencji."
        )
    parts.append(irrigation.legal_note)
    return CoreRecommendation(
        category="nawadnianie",
        title=title,
        justification=" ".join(parts),
        evidence_ids=["E01", "E06", "E11", "E22"],
        priority=1 if irrigation.status == "zalecane" else 2,
    )


def interpret(
    parcel: Parcel, water: WaterState, soil: SoilInfo, irrigation: IrrigationAdvice, land: LandObservation
) -> LandInterpretation:
    result = from_core(land)
    sections = confidence.assess(water, soil, result)
    core_confidence = [
        CoreConfidence(section=s.section, level=s.level.value, reason="; ".join(s.reasons)) for s in sections
    ]
    if water is None:
        return LandInterpretation(confidence=core_confidence)
    level = assess(water, result).risk_level
    found = causes.identify(water, soil, result)
    active = [c for c in found if c.active]
    core_causes = [
        CoreCause(
            code=CAUSE_CODES[c.key],
            label=c.label,
            contribution_mm=c.contribution_mm,
            rank=i,
            evidence=f"{c.explanation} Źródła: {', '.join(c.evidence)}.",
        )
        for i, c in enumerate(active, 1)
    ]
    rec_level = next(s.level for s in sections if s.section == "rekomendacje")
    ctx = context.build(
        water.crop,
        water.analysis_date,
        parcel.is_agricultural,
        parcel.area_ha,
        water,
        soil,
        irrigation,
        result,
        found,
        level,
    )
    recs = [_recommendation(r) for r in retention.recommend(ctx, result, rec_level) + agro.recommend(ctx, rec_level)]
    extra = irrigation_recommendation(irrigation, result.hydro.groundwater if result.hydro else None)
    if extra is not None:
        recs.append(extra)
    return LandInterpretation(causes=core_causes, recommendations=recs, confidence=core_confidence)
