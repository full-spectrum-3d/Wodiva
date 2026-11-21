import logging
import uuid
from datetime import UTC, datetime

from app.core.contracts import ReportInput
from app.core.schemas import DataSource, Report
from app.land import service
from app.land.geo import parcel_geometry
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
    store.save(report, map_png)
    return report
