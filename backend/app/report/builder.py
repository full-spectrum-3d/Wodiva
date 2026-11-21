import logging
import uuid
from datetime import UTC, datetime

from app.core.contracts import ReportInput
from app.core.schemas import DataSource, Report
from app.land import overlay, service
from app.land.geo import PL_CRS, parcel_geometry
from app.report import maps, store
from app.report.summary import risk

log = logging.getLogger("wodiva.report")
CATEGORY_ORDER = {"retencja": 0, "agrotechnika": 1, "nawadnianie": 2}


def _unique(sources: list[DataSource]) -> list[DataSource]:
    seen, out = set(), []
    for s in sources:
        key = (s.name, s.url, s.status)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def build(data: ReportInput) -> Report:
    recommendations = []
    if data.water is not None:
        recommendations = sorted(
            data.interpretation.recommendations, key=lambda r: (CATEGORY_ORDER[r.category], r.priority)
        )
    report = Report(
        id=uuid.uuid4().hex[:12],
        created_at=datetime.now(UTC),
        analysis_date=data.analysis_date,
        crop=data.crop,
        parcel=data.parcel,
        water=data.water,
        soil=data.soil,
        satellite=data.land.satellite,
        terrain=data.land.terrain,
        hydro=data.land.hydro,
        causes=data.interpretation.causes if data.water is not None else [],
        recommendations=recommendations,
        irrigation=data.irrigation,
        confidence=data.interpretation.confidence,
        sources=_unique(data.sources),
        limitations=data.limitations,
        timings_s=data.timings_s,
    )
    return persist(report)


def persist(report: Report) -> Report:
    report.summary = risk(report)
    map_png = None
    artifacts = service.artifacts_for(report.parcel.id, report.analysis_date)
    try:
        map_png = maps.render(parcel_geometry(report.parcel.geometry_wkt_2180), artifacts)
    except Exception:
        log.exception("map rendering failed")
    _save_overlays(report, artifacts)
    store.save(report, map_png)
    return report


def _terrain_overlays(report: Report, artifacts) -> dict[str, dict]:
    if artifacts is None or artifacts.terrain is None or artifacts.dem is None:
        return {}
    geom = parcel_geometry(report.parcel.geometry_wkt_2180)
    rasters = {"slope": artifacts.terrain.slope_pct, "twi": artifacts.terrain.twi}
    found = {}
    for name, values in rasters.items():
        try:
            rendered = overlay.render(name, values, artifacts.dem.transform, PL_CRS, geom)
        except Exception:
            log.exception("overlay %s failed", name)
            rendered = None
        if rendered is not None:
            found[name] = rendered
    return found


def _save_overlays(report: Report, artifacts) -> None:
    rendered = {**(artifacts.overlays if artifacts is not None else {}), **_terrain_overlays(report, artifacts)}
    satellite, terrain = {}, {}
    for name, item in rendered.items():
        store.save_overlay(report.id, name, item["png"])
        info = {"url": f"/api/report/{report.id}/overlay/{name}.png", "bounds": item["bounds"], **overlay.legend(name)}
        if name in overlay.SATELLITE:
            scene = report.satellite.last_scene_date if report.satellite else None
            info["date"] = scene.isoformat() if scene else None
            satellite[name] = info
        else:
            info["source"] = report.terrain.details.get("terrain", {}).get("dem_source") if report.terrain else None
            terrain[name] = info
    if satellite and report.satellite is not None:
        report.satellite.details["overlays"] = satellite
        if "ndvi" in satellite:
            report.satellite.details["ndvi_overlay"] = {**satellite["ndvi"], "url": f"/api/report/{report.id}/ndvi.png"}
    if terrain and report.terrain is not None:
        report.terrain.details["overlays"] = terrain
