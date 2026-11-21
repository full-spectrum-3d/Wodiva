import uuid
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
from shapely.geometry import box

from app.core.schemas import (
    AnalyzeRequest,
    Cause,
    Confidence,
    DataSource,
    HydroInfo,
    Limitation,
    MeteoSeries,
    Recommendation,
    Report,
    SatelliteState,
    SourceStatus,
    TerrainInfo,
)
from app.water import meteo
from app.water.engine.crops import get_crop
from app.water.parcel import build_parcel
from app.water.service import WaterPrep, compute
from app.water.soil import layers_from_category, summarize

MOCK_ID = "060802_2.0001.MOCK"


def synthetic_weather(start: date, end: date, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = [d.date() for d in pd.date_range(start, end, freq="D")]
    doy = np.array([d.timetuple().tm_yday for d in idx])
    season = np.sin(2 * np.pi * (doy - 105) / 365)
    tmax = 13 + 12 * season + rng.normal(0, 3, len(idx))
    tmin = tmax - 8 - rng.normal(0, 1.5, len(idx))
    wet = rng.random(len(idx)) < 0.38
    precip = np.where(wet, rng.gamma(0.9, 4.2, len(idx)), 0.0)
    rs = np.clip(10 + 9 * season + rng.normal(0, 3, len(idx)), 1, 30)
    return pd.DataFrame(
        {
            "precip_mm": precip,
            "tmax_c": tmax,
            "tmin_c": tmin,
            "tdew_c": tmin - 1,
            "wind10_ms": np.full(len(idx), 3.5),
            "rs_mj": rs,
            "pressure_kpa": np.full(len(idx), 100.5),
        },
        index=pd.Index(idx, name="date"),
    )


def mock_report(req: AnalyzeRequest) -> Report:
    geom = box(745000, 370000, 745200, 370150)
    parcel = build_parcel(
        {
            "id": MOCK_ID,
            "teryt": "060802_2",
            "voivodeship": "lubelskie",
            "county": "puławski",
            "commune": "Puławy",
            "region": "0001",
            "parcel": "MOCK",
            "geom_wkt": geom.wkt,
        },
        "atrapa",
    )
    parcel.is_agricultural = True
    frame = meteo.with_et0(synthetic_weather(meteo.history_start(req.date, 10), req.date), parcel.centroid_lat)
    category = req.soil_category or "II"
    soil = summarize(layers_from_category(category), category, "atrapa", "kategoria IUNG")
    series = MeteoSeries(lat=parcel.centroid_lat, lon=parcel.centroid_lon, cell_id="mock", days=[])
    prep = WaterPrep(
        parcel=parcel,
        analysis_date=req.date,
        crop=get_crop(req.crop),
        meteo=meteo.MeteoResult(frame=frame, forecast=frame.iloc[0:0], series=series),
        soil=soil,
        station_check=None,
    )
    result = compute(prep, slope_pct=3.0, phase_offset_days=None)
    now = datetime.now(UTC)
    return Report(
        id="mock-" + uuid.uuid4().hex[:8],
        created_at=now,
        analysis_date=req.date,
        crop=req.crop,
        parcel=parcel,
        water=result.state,
        soil=result.soil,
        satellite=SatelliteState(
            scenes_used=4, ndvi=0.62, ndmi=0.08, vci=31.0, crop_phase="pełnia", surface_state="roślinność"
        ),
        terrain=TerrainInfo(slope_mean_pct=3.0, slope_max_pct=7.5, twi_mean=6.1),
        hydro=HydroInfo(ditches=[{"name": "rów R-12", "distance_m": 140}]),
        causes=[
            Cause(code="opad", label="Niedobór opadów", contribution_mm=-48.0, rank=1, evidence="atrapa"),
            Cause(code="gleba", label="Niska retencja gleby", contribution_mm=None, rank=2, evidence="atrapa"),
        ],
        recommendations=[
            Recommendation(category="retencja", title="Zastawka na rowie R-12", justification="atrapa"),
            Recommendation(category="agrotechnika", title="Międzyplon ścierniskowy", justification="atrapa"),
        ],
        irrigation=result.irrigation,
        confidence=[Confidence(section="ocena", level="średnia", reason="atrapa")],
        sources=[
            DataSource(
                name="Dane syntetyczne (atrapa)",
                url="-",
                license="-",
                retrieved_at=now,
                status=SourceStatus.partial,
            )
        ],
        limitations=[
            Limitation(code="mock", message="To jest raport testowy na danych syntetycznych.", severity="krytyczne"),
            *result.limitations,
        ],
        mock=True,
    )
