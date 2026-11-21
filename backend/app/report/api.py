import asyncio
import re
from functools import cache

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.schemas import Report
from app.land.settings import data_dir
from app.report import pdf, store
from app.report.summary import ReportSummary, summarize

router = APIRouter()
REPORT_ID = re.compile(r"^[0-9a-f]{12}$")
EVIDENCE_ROW = re.compile(r"^\|\s*(E\d+)\s*\|(.+)\|(.+)\|\s*$")


class EvidenceItem(BaseModel):
    id: str
    source: str
    purpose: str


@cache
def evidence_items() -> dict[str, EvidenceItem]:
    rows = (EVIDENCE_ROW.match(line) for line in (data_dir() / "evidence.md").read_text(encoding="utf-8").splitlines())
    return {
        m[1]: EvidenceItem(id=m[1], source=m[2].strip(), purpose=m[3].strip())
        for m in rows
        if m
    }


def load(report_id: str) -> Report:
    report = store.load(report_id) if REPORT_ID.match(report_id) else None
    if report is None:
        raise HTTPException(404, "Nie ma takiego raportu.")
    return report


@router.get("/report/{report_id}.pdf")
async def report_pdf(report_id: str) -> Response:
    report = load(report_id)
    content = await asyncio.to_thread(pdf.render, report, store.load_map(report_id))
    filename = f"wodiva_{report.parcel.id.replace('/', '-')}_{report.analysis_date}.pdf"
    return Response(
        content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@router.get("/report/{report_id}/map.png")
async def report_map(report_id: str) -> Response:
    load(report_id)
    png = store.load_map(report_id)
    if png is None:
        raise HTTPException(404, "Brak mapy dla tego raportu.")
    return Response(png, media_type="image/png")


@router.get("/report/{report_id}/ndvi.png")
async def report_ndvi(report_id: str) -> Response:
    load(report_id)
    png = store.load_overlay(report_id, "ndvi")
    if png is None:
        raise HTTPException(404, "Brak nakładki NDVI dla tego raportu.")
    return Response(png, media_type="image/png")


@router.get("/report/{report_id}/summary", response_model=ReportSummary)
async def report_summary(report_id: str) -> ReportSummary:
    return summarize(load(report_id))


@router.get("/report/{report_id}", response_model=Report)
async def report_json(report_id: str) -> Report:
    return load(report_id)


@router.get("/evidence")
async def evidence() -> Response:
    return Response((data_dir() / "evidence.md").read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@router.get("/evidence/{evidence_id}", response_model=EvidenceItem)
async def evidence_item(evidence_id: str) -> EvidenceItem:
    item = evidence_items().get(evidence_id.upper())
    if item is None:
        raise HTTPException(404, "Nie ma takiej pozycji w rejestrze źródeł.")
    return item
