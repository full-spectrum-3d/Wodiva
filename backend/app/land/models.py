from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DataStatus(StrEnum):
    ok = "ok"
    partial = "częściowo"
    missing = "brak"


class Level(StrEnum):
    high = "wysoka"
    medium = "średnia"
    low = "niska"


class SatelliteObservation(BaseModel):
    date: dt.date
    scene_id: str
    sensor: str = "Sentinel-2"
    ndvi: float | None = None
    ndmi: float | None = None
    ndwi: float | None = None
    ndre: float | None = None
    clear_fraction: float
    effective_pixels: float


class SatelliteState(BaseModel):
    latest: SatelliteObservation | None = None
    history: list[SatelliteObservation] = Field(default_factory=list)
    phase: str
    phase_label: str
    interpretable: bool
    vci_ndvi: float | None = None
    vci_ndmi: float | None = None
    anomaly_class: str | None = None
    interpretation: str
    sharpened: bool = False
    phase_offset_days: int | None = None
    surface_state: str = "nieznany"
    season_points: int = 0
    status: DataStatus = DataStatus.ok


class RadarObservation(BaseModel):
    date: dt.date
    scene_id: str
    vv_db: float
    vh_db: float
    vh_vv_db: float


class RadarState(BaseModel):
    latest: RadarObservation | None = None
    reference_years: int = 0
    vv_anomaly_db: float | None = None
    vh_vv_anomaly_db: float | None = None
    recent_rain: bool = False
    interpretation: str
    status: DataStatus = DataStatus.ok


class GeoFeature(BaseModel):
    kind: str
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class TerrainInfo(BaseModel):
    dem_source: str
    resolution_m: float
    mean_slope_pct: float | None = None
    max_slope_pct: float | None = None
    twi_mean: float | None = None
    runoff_risk: Level | None = None
    depression_area_m2: float = 0.0
    depression_volume_m3: float = 0.0
    flow_path_length_m: float = 0.0
    outflow_share: float | None = None
    features: list[GeoFeature] = Field(default_factory=list)
    status: DataStatus = DataStatus.ok


class HydroInfo(BaseModel):
    ditch_distance_m: float | None = None
    watercourse_distance_m: float | None = None
    water_body_distance_m: float | None = None
    wetland_distance_m: float | None = None
    ditch_in_parcel: bool = False
    watercourse_in_parcel: bool = False
    water_area_ha_500m: float = 0.0
    wetland_area_ha_500m: float = 0.0
    tree_cover_pct_500m: float = 0.0
    tree_cover_pct_parcel: float = 0.0
    water_pct_parcel: float = 0.0
    hydrotechnical_within_500m: bool = False
    search_radius_m: float = 500.0
    status: DataStatus = DataStatus.ok


class DroughtContext(BaseModel):
    date: dt.date | None = None
    cdi_class: str | None = None
    cdi_meaning: str | None = None
    status: DataStatus = DataStatus.ok


class Cause(BaseModel):
    key: str
    label: str
    active: bool
    score: float
    contribution_mm: float | None = None
    explanation: str
    evidence: list[str] = Field(default_factory=list)


class SectionConfidence(BaseModel):
    section: str
    level: Level
    score: float
    reasons: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    key: str
    category: str
    priority: int
    title: str
    action: str
    rationale: str
    cause_keys: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    ecoscheme: str | None = None
    location: GeoFeature | None = None
    confidence: Level = Level.medium


class LandSourceNote(BaseModel):
    key: str
    status: DataStatus = DataStatus.ok
    period_start: dt.date | None = None
    period_end: dt.date | None = None
    note: str | None = None


class LandNote(BaseModel):
    code: str
    section: str
    text: str
    severity: str = "info"


class LandResult(BaseModel):
    satellite: SatelliteState | None = None
    radar: RadarState | None = None
    terrain: TerrainInfo | None = None
    hydro: HydroInfo | None = None
    drought: DroughtContext | None = None
    sources: list[LandSourceNote] = Field(default_factory=list)
    notes: list[LandNote] = Field(default_factory=list)
    timings_s: dict[str, float] = Field(default_factory=dict)
