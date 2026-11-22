import type { Geometry } from 'geojson';

// Odwzorowanie backend/app/core/schemas.py — tylko pola używane przez UI.
export interface Parcel {
  id: string;
  commune: string | null;
  region: string | null;
  county: string | null;
  number: string | null;
  area_ha: number;
  is_agricultural: boolean | null;
  land_use?: { code: string; soil_class: string | null; share: number | null }[];
  /** Granica działki, GeoJSON w WGS84 (EPSG:4326). */
  geometry_geojson?: Geometry;
}

export interface ParcelCandidate {
  id: string;
  commune: string | null;
  region: string | null;
  county: string | null;
}

export interface Crop {
  code: string;
  name: string;
  critical_period: string;
  critical_label: string;
}

export interface AnalyzeRequest {
  parcel_id: string;
  date: string;
  crop: string;
}

export interface ApiError {
  status: number;
  message: string;
  candidates: ParcelCandidate[];
}

// backend/app/assistant/kolba.py
export interface AssistantAnswer {
  answer: string;
  /** 'AI' | 'bez AI' | 'bez AI (model niedostępny)' */
  mode: string;
  evidence: string[];
}
