import asyncio
import importlib
import logging
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.core.contracts import LandInterpretation, LandObservation, ReportInput
from app.core.http import SourceError, timings
from app.core.mock import mock_report
from app.core.schemas import AnalyzeRequest, Limitation, Report
from app.core.validation import InputError, validate_analysis_date
from app.water import service as water
from app.water.engine.crops import load_crops
from app.water.parcel import ParcelLookupError, resolve_by_id

log = logging.getLogger("wodiva.analyze")
router = APIRouter()

LAND_TIMEOUT_S = 22


def _optional(module: str):
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name and module.startswith(exc.name):
            return None
        raise


def default_build(data: ReportInput) -> Report:
    return Report(
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
        causes=data.interpretation.causes,
        recommendations=data.interpretation.recommendations,
        irrigation=data.irrigation,
        confidence=data.interpretation.confidence,
        sources=data.sources,
        limitations=data.limitations,
        timings_s=data.timings_s,
    )


async def _observe(land, parcel, day, crop) -> LandObservation:
    if land is None:
        return LandObservation(
            limitations=[Limitation(code="land_missing", message="Moduł satelita/teren/hydrologia niedostępny.")]
        )
    try:
        return await asyncio.wait_for(land.observe(parcel, day, crop), timeout=LAND_TIMEOUT_S)
    except Exception as exc:
        log.exception("land.observe failed")
        return LandObservation(
            limitations=[
                Limitation(
                    code="land_error",
                    message=f"Nie udało się pobrać danych satelitarnych/terenowych ({type(exc).__name__}).",
                    severity="ostrzeżenie",
                )
            ]
        )


async def run_analysis(req: AnalyzeRequest) -> Report:
    store: dict[str, float] = {}
    token = timings.set(store)
    started = time.perf_counter()
    try:
        validate_analysis_date(req.date)
        if req.crop not in load_crops():
            raise InputError(f"Nieznana uprawa: {req.crop}")
        parcel, parcel_sources = await resolve_by_id(req.parcel_id)
        land = _optional("app.land.service")
        prep, obs = await asyncio.gather(
            water.prepare(parcel, req.date, req.crop, req.soil_category),
            _observe(land, parcel, req.date, req.crop),
        )
        slope = obs.terrain.slope_mean_pct if obs.terrain else None
        phase = obs.satellite.phase_offset_days if obs.satellite else None
        result = water.compute(prep, slope, phase)
        interp = LandInterpretation()
        if land is not None:
            interp = land.interpret(parcel, result.state, result.soil, result.irrigation, obs)
        store["total"] = round(time.perf_counter() - started, 2)
        data = ReportInput(
            parcel=parcel,
            analysis_date=req.date,
            crop=req.crop,
            water=result.state,
            soil=result.soil,
            irrigation=result.irrigation,
            land=obs,
            interpretation=interp,
            sources=[*parcel_sources, *result.sources, *obs.sources],
            limitations=[*result.limitations, *obs.limitations, *interp.limitations],
            timings_s=dict(store),
        )
        builder = _optional("app.report.builder")
        return builder.build(data) if builder is not None else default_build(data)
    finally:
        timings.reset(token)


@router.post("/analyze", response_model=Report)
async def analyze(req: AnalyzeRequest, mock: bool = Query(False)) -> Report:
    if mock or get_settings().analyze_mock:
        report = mock_report(req)
        builder = _optional("app.report.builder")
        return builder.persist(report) if builder is not None else report
    try:
        return await run_analysis(req)
    except InputError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ParcelLookupError as exc:
        raise HTTPException(404, {"message": str(exc), "candidates": exc.candidates}) from exc
    except SourceError as exc:
        raise HTTPException(503, f"Źródło danych niedostępne: {exc}") from exc
