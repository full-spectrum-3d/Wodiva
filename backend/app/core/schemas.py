from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceStatus(StrEnum):
    ok = "ok"
    missing = "brak"
    partial = "częściowo"


class DataSource(BaseModel):
    name: str
    url: str
    license: str
    retrieved_at: datetime
    period_start: date | None = None
    period_end: date | None = None
    status: SourceStatus = SourceStatus.ok
    note: str | None = None


class Limitation(BaseModel):
    code: str
    message: str
    severity: Literal["info", "ostrzeżenie", "krytyczne"] = "info"
    section: str | None = None


class LandUseShare(BaseModel):
    code: str
    soil_class: str | None = None
    share: float | None = None


class Parcel(BaseModel):
    id: str
    teryt: str | None = None
    voivodeship: str | None = None
    county: str | None = None
    commune: str | None = None
    region: str | None = None
    number: str | None = None
    geometry_wkt_2180: str
    geometry_geojson: dict[str, Any]
    area_ha: float
    perimeter_m: float
    centroid_lat: float
    centroid_lon: float
    parts: int = 1
    land_use: list[LandUseShare] = Field(default_factory=list)
    is_agricultural: bool | None = None
    land_use_checked: bool = False
    size_class: Literal["mała", "średnia", "duża"]
    flags: list[str] = Field(default_factory=list)
    source: str = "ULDK"


class MeteoDay(BaseModel):
    date: date
    precip_mm: float | None = None
    tmax_c: float | None = None
    tmin_c: float | None = None
    tdew_c: float | None = None
    wind10_ms: float | None = None
    rs_mj: float | None = None
    pressure_kpa: float | None = None
    et0_mm: float | None = None
    source: Literal["era5", "openmeteo", "imgw", "prognoza", "uzupełnione"] = "era5"


class StationCheck(BaseModel):
    station_code: str
    station_name: str
    distance_km: float
    period_start: date
    period_end: date
    days_compared: int
    precip_model_mm: float
    precip_station_mm: float
    precip_diff_pct: float | None
    tmean_bias_c: float | None
    latest_obs: dict[str, Any] | None = None


class MeteoSeries(BaseModel):
    lat: float
    lon: float
    cell_id: str
    days: list[MeteoDay]
    forecast: list[MeteoDay] = Field(default_factory=list)
    era5_until: date | None = None
    station_check: StationCheck | None = None


class SoilLayer(BaseModel):
    top_cm: int
    bottom_cm: int
    sand_pct: float
    silt_pct: float
    clay_pct: float
    soc_pct: float
    theta_fc: float
    theta_wp: float
    awc: float


class SoilInfo(BaseModel):
    layers: list[SoilLayer]
    texture_topsoil: str
    iung_category: Literal["I", "II", "III", "IV"] | None
    iung_category_source: str
    awc_mm_100cm: float
    organic_matter_pct_topsoil: float
    source: Literal["SoilGrids", "kategoria IUNG", "wartość domyślna"]
    agreement: str | None = None
    confidence: Literal["wysoka", "średnia", "niska"] = "średnia"


class DecadeRisk(BaseModel):
    month: int
    decade: int
    label: str
    stress_freq: float | None
    kbw_deficit_freq: float | None


class ClimateIndicators(BaseModel):
    kbw_60d_mm: float
    kbw_period_label: str | None
    kbw_period_mm: float | None
    kbw_threshold_mm: float | None
    kbw_drought: bool | None
    kbw_percentile: float | None
    spi_1: float | None
    spi_3: float | None
    precip_30d_mm: float
    precip_30d_norm_mm: float | None
    et0_30d_mm: float
    et0_anomaly_pct: float | None
    hot_days_30d: int
    hot_days_season: int
    dry_spell_current_days: int
    dry_spell_max_90d_days: int
    years_analyzed: list[int]
    seasons_with_kbw_drought: list[int]
    risk_calendar: list[DecadeRisk]


class SoilWaterDay(BaseModel):
    date: date
    depletion_mm: float
    taw_mm: float
    raw_mm: float
    ks: float
    precip_mm: float
    etc_mm: float
    in_season: bool


class SoilWaterState(BaseModel):
    date: date
    in_season: bool
    stage: str
    root_depth_m: float
    taw_mm: float
    raw_mm: float
    depletion_mm: float
    available_pct: float
    ks: float
    percentile_10y: float | None
    stress_days_season: int
    stress_days_by_year: dict[int, int]
    runoff_season_mm: float
    last_90_days: list[SoilWaterDay]


class ScenarioResult(BaseModel):
    code: str
    name: str
    description: str
    reference_year: int
    stress_days_baseline: int
    stress_days_scenario: int
    stress_days_saved: int
    available_pct_baseline: float
    available_pct_scenario: float


class IrrigationAdvice(BaseModel):
    status: Literal["zalecane", "niezalecane", "monitoruj", "nie dotyczy"]
    reason: str
    first_day: date | None = None
    net_dose_mm: float | None = None
    gross_dose_mm: float | None = None
    split_into: int | None = None
    volume_m3: float | None = None
    forecast_precip_7d_mm: float | None = None
    forecast_etc_7d_mm: float | None = None
    forecast_available: bool = False
    legal_note: str


class WaterState(BaseModel):
    analysis_date: date
    crop: str
    crop_name: str
    meteo_until: date
    era5_until: date | None
    climate: ClimateIndicators
    soil_water: SoilWaterState | None
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    station_check: StationCheck | None = None
    meteo_last_90: list[MeteoDay] = Field(default_factory=list)
    forecast: list[MeteoDay] = Field(default_factory=list)


class SatelliteState(BaseModel):
    scenes_used: int = 0
    last_scene_date: date | None = None
    ndvi: float | None = None
    ndmi: float | None = None
    vci: float | None = None
    crop_phase: str | None = None
    phase_offset_days: int | None = None
    surface_state: Literal["roślinność", "goła gleba", "po zbiorze", "nieznany"] = "nieznany"
    s1_anomaly_db: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TerrainInfo(BaseModel):
    slope_mean_pct: float | None = None
    slope_max_pct: float | None = None
    twi_mean: float | None = None
    depressions: list[dict[str, Any]] = Field(default_factory=list)
    flow_lines: list[dict[str, Any]] = Field(default_factory=list)
    tree_cover_buffer_pct: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HydroInfo(BaseModel):
    watercourses: list[dict[str, Any]] = Field(default_factory=list)
    water_bodies: list[dict[str, Any]] = Field(default_factory=list)
    ditches: list[dict[str, Any]] = Field(default_factory=list)
    wetlands: list[dict[str, Any]] = Field(default_factory=list)
    groundwater: dict[str, Any] | None = None
    edo: dict[str, Any] | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class Cause(BaseModel):
    code: Literal["opad", "upał", "gleba", "spływ", "retencja", "inne"]
    label: str
    contribution_mm: float | None = None
    rank: int
    evidence: str


class Recommendation(BaseModel):
    category: Literal["retencja", "agrotechnika", "nawadnianie"]
    title: str
    justification: str
    evidence_ids: list[str] = Field(default_factory=list)
    eco_scheme: str | None = None
    priority: int = 2
    location: dict[str, Any] | None = None


class Confidence(BaseModel):
    section: str
    level: Literal["wysoka", "średnia", "niska"]
    reason: str


class AnalyzeRequest(BaseModel):
    parcel_id: str = Field(min_length=3, max_length=80)
    date: date
    crop: str = Field(min_length=2, max_length=40)
    soil_category: Literal["I", "II", "III", "IV"] | None = None


class RiskSummary(BaseModel):
    status: str
    risk_level: str | None = None
    headline: str
    findings: list[str] = Field(default_factory=list)


class Report(BaseModel):
    id: str
    created_at: datetime
    analysis_date: date
    crop: str
    parcel: Parcel
    water: WaterState | None
    soil: SoilInfo | None
    satellite: SatelliteState | None = None
    terrain: TerrainInfo | None = None
    hydro: HydroInfo | None = None
    causes: list[Cause] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    irrigation: IrrigationAdvice | None = None
    confidence: list[Confidence] = Field(default_factory=list)
    sources: list[DataSource] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    timings_s: dict[str, float] = Field(default_factory=dict)
    mock: bool = False
    summary: RiskSummary | None = None
