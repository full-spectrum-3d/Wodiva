// Odwzorowanie backend/app/core/schemas.py (Report) i app/report/summary.py — tylko pola używane przez UI.
import type { Geometry } from 'geojson';

import { Parcel } from './wodiva-api.model';

export type SourceStatus = 'ok' | 'brak' | 'częściowo';
export type ConfidenceLevel = 'wysoka' | 'średnia' | 'niska';

export interface DataSource {
  name: string;
  url: string;
  license: string;
  retrieved_at: string;
  period_start: string | null;
  period_end: string | null;
  status: SourceStatus;
  note: string | null;
}

export interface Limitation {
  code: string;
  message: string;
  severity: 'info' | 'ostrzeżenie' | 'krytyczne';
  section: string | null;
}

export interface DecadeRisk {
  month: number;
  decade: number;
  label: string;
  stress_freq: number | null;
  kbw_deficit_freq: number | null;
}

export interface ClimateIndicators {
  kbw_60d_mm: number;
  kbw_period_label: string | null;
  kbw_period_mm: number | null;
  kbw_threshold_mm: number | null;
  kbw_drought: boolean | null;
  precip_30d_mm: number;
  precip_30d_norm_mm: number | null;
  dry_spell_current_days: number;
  years_analyzed: number[];
  risk_calendar: DecadeRisk[];
}

export interface SoilWaterState {
  available_pct: number;
  percentile_10y: number | null;
  stress_days_season: number;
  in_season: boolean;
  stage: string;
}

export interface ScenarioResult {
  code: string;
  name: string;
  description: string;
  reference_year: number;
  stress_days_baseline: number;
  stress_days_scenario: number;
  stress_days_saved: number;
}

export interface WaterState {
  crop_name: string;
  meteo_until: string;
  climate: ClimateIndicators;
  soil_water: SoilWaterState | null;
  scenarios: ScenarioResult[];
}

export interface Cause {
  code: string;
  label: string;
  contribution_mm: number | null;
  rank: number;
  evidence: string;
}

export interface Recommendation {
  category: 'retencja' | 'agrotechnika' | 'nawadnianie';
  title: string;
  justification: string;
  evidence_ids: string[];
  eco_scheme: string | null;
  priority: number;
  /** Miejsce zalecenia na mapie: land/models.py GeoFeature (geometria WGS84). */
  location: { kind: string; geometry: Geometry; properties?: Record<string, unknown> } | null;
}

export interface IrrigationAdvice {
  status: 'zalecane' | 'niezalecane' | 'monitoruj' | 'nie dotyczy';
  reason: string;
  first_day: string | null;
  net_dose_mm: number | null;
  gross_dose_mm: number | null;
  split_into: number | null;
  volume_m3: number | null;
  forecast_precip_7d_mm: number | null;
  forecast_etc_7d_mm: number | null;
  forecast_available: boolean;
  legal_note: string;
}

export interface Confidence {
  section: string;
  level: ConfidenceLevel;
  reason: string;
}

/** Nakładka rastrowa z backendu: wskaźniki Sentinel-2 (satellite.details.overlays) i terenu (terrain.details.overlays). */
export interface RasterOverlay {
  url: string;
  bounds: [[number, number], [number, number]];
  date?: string | null;
  range: [number, number];
  colors: string[];
  opacity: number;
  label?: string;
  description?: string;
  unit?: string;
}

export type NdviOverlay = RasterOverlay;

export interface SatelliteState {
  ndvi: number | null;
  ndmi: number | null;
  vci: number | null;
  last_scene_date: string | null;
  details: { ndvi_overlay?: RasterOverlay; overlays?: Record<string, RasterOverlay> } & Record<string, unknown>;
}

export interface Depression {
  geometry: Geometry;
  area_m2?: number;
  max_depth_m?: number;
  volume_m3?: number;
  inside_parcel_share?: number;
}

export interface FlowLine {
  geometry: Geometry;
  length_m?: number;
  max_contributing_area_ha?: number;
}

export interface TerrainInfo {
  slope_mean_pct: number | null;
  slope_max_pct: number | null;
  depressions: Depression[];
  flow_lines: FlowLine[];
  tree_cover_buffer_pct: number | null;
  details?: { overlays?: Record<string, RasterOverlay> } & Record<string, unknown>;
}

/** Rów, ciek albo zbiornik z BDOT10k (kształt w promieniu 500 m, punkt najbliżej środka działki). */
export interface WaterObject {
  geometry?: Geometry;
  nearest_point?: { lon: number; lat: number };
  type?: string;
  distance_m?: number;
  width_m?: number;
  mphp_id?: string;
}

export interface Well {
  id?: string;
  place?: string | null;
  lon: number | null;
  lat: number | null;
  distance_km?: number;
  water_table_depth_m?: number;
  measured_on?: string;
  aquifer?: string | null;
}

export interface HydroInfo {
  ditches: WaterObject[];
  watercourses: WaterObject[];
  water_bodies: WaterObject[];
  groundwater: { wells?: Well[]; body?: { quantitative_status?: string | null } & Record<string, unknown> } | null;
  edo: { date?: string | null; cdi_class?: string | null; cdi_meaning?: string | null } | null;
}

export interface Report {
  id: string;
  created_at: string;
  analysis_date: string;
  crop: string;
  parcel: Parcel;
  water: WaterState | null;
  satellite?: SatelliteState | null;
  terrain?: TerrainInfo | null;
  hydro?: HydroInfo | null;
  causes: Cause[];
  recommendations: Recommendation[];
  irrigation: IrrigationAdvice | null;
  confidence: Confidence[];
  sources: DataSource[];
  limitations: Limitation[];
  /** Raport z ?mock=true — zapisywany i obsługiwany jak zwykły, różni się tylko tą flagą. */
  mock: boolean;
  /** Ocena ryzyka liczona przez backend przy zapisie; null w raportach sprzed tej zmiany. */
  summary?: RiskSummary | null;
}

/** core/schemas.py: RiskSummary */
export interface RiskSummary {
  status: string;
  risk_level: ConfidenceLevel | null;
  headline: string;
  findings: string[];
}

/** report/summary.py: ReportSummary — GET /report/{id}/summary */
export interface ReportSummary extends RiskSummary {
  report_id: string;
}

/** report/api.py: EvidenceItem — GET /evidence/{id} */
export interface EvidenceItem {
  id: string;
  source: string;
  purpose: string;
}
