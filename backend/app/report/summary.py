from pydantic import BaseModel, Field

from app.core.contracts import LandObservation
from app.core.schemas import Report
from app.land.assessment import assess
from app.land.service import from_core


class ReportSummary(BaseModel):
    report_id: str
    status: str
    risk_level: str | None
    headline: str
    findings: list[str] = Field(default_factory=list)


def summarize(report: Report) -> ReportSummary:
    land = from_core(LandObservation(satellite=report.satellite, terrain=report.terrain, hydro=report.hydro))
    result = assess(report.water, land)
    return ReportSummary(
        report_id=report.id,
        status=result.status.value,
        risk_level=result.risk_level.value if result.risk_level else None,
        headline=result.headline,
        findings=result.findings,
    )
