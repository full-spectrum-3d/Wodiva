from app.core.contracts import LandObservation
from app.core.schemas import Report, RiskSummary
from app.land.assessment import assess
from app.land.service import from_core


class ReportSummary(RiskSummary):
    report_id: str


def risk(report: Report) -> RiskSummary:
    land = from_core(LandObservation(satellite=report.satellite, terrain=report.terrain, hydro=report.hydro))
    result = assess(report.water, land)
    return RiskSummary(
        status=result.status.value,
        risk_level=result.risk_level.value if result.risk_level else None,
        headline=result.headline,
        findings=result.findings,
    )


def summarize(report: Report) -> ReportSummary:
    return ReportSummary(report_id=report.id, **(report.summary or risk(report)).model_dump())
