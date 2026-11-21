// Odwzorowanie backend/app/core/schemas.py (Report) i app/report/summary.py — tylko pola używane przez UI.
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
  location: Record<string, unknown> | null;
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

export interface Report {
  id: string;
  created_at: string;
  analysis_date: string;
  crop: string;
  parcel: Parcel;
  water: WaterState | null;
  causes: Cause[];
  recommendations: Recommendation[];
  irrigation: IrrigationAdvice | null;
  confidence: Confidence[];
  sources: DataSource[];
  limitations: Limitation[];
  mock: boolean;
}

export interface ReportSummary {
  report_id: string;
  status: string;
  risk_level: ConfidenceLevel | null;
  headline: string;
  findings: string[];
}
