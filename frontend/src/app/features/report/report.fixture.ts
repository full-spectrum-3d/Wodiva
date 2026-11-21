import { Report } from '../../core/report.model';

/** Raport testowy w kształcie backend/app/core/schemas.py:Report (wartości wymyślone). */
export function reportFixture(overrides: Partial<Report> = {}): Report {
  const calendar = Array.from({ length: 36 }, (_, i) => ({
    month: Math.floor(i / 3) + 1,
    decade: (i % 3) + 1,
    label: `${['I', 'II', 'III'][i % 3]} dekada ${Math.floor(i / 3) + 1}`,
    stress_freq: i >= 12 && i < 21 ? 0.6 : 0.1,
    kbw_deficit_freq: null,
  }));
  return {
    id: 'abc123def456',
    created_at: '2026-07-01T10:00:00Z',
    analysis_date: '2026-07-01',
    crop: 'kukurydza',
    parcel: { id: '141201_1.0001.6509', commune: 'Pionki', region: 'Krzewina', county: null, number: '6509', area_ha: 1.24, is_agricultural: true },
    water: {
      crop_name: 'Kukurydza na ziarno',
      meteo_until: '2026-06-30',
      climate: {
        kbw_60d_mm: -92.4,
        kbw_threshold_mm: -70,
        kbw_drought: true,
        precip_30d_mm: 18.2,
        precip_30d_norm_mm: 64,
        dry_spell_current_days: 12,
        kbw_period_label: 'maj–czerwiec',
        kbw_period_mm: -84,
        years_analyzed: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
        risk_calendar: calendar,
      },
      soil_water: { available_pct: 27.6, percentile_10y: 20, stress_days_season: 14, in_season: true, stage: 'rozwój' },
      scenarios: [
        { code: 'om', name: 'Więcej próchnicy', description: '+1% materii organicznej', reference_year: 2025, stress_days_baseline: 20, stress_days_scenario: 15, stress_days_saved: 5 },
      ],
    },
    causes: [
      { code: 'upał', label: 'Wysokie parowanie', contribution_mm: 40, rank: 2, evidence: 'ET0 o 25% powyżej normy' },
      { code: 'opad', label: 'Mało deszczu', contribution_mm: 46, rank: 1, evidence: 'Opad 28% normy z 30 dni' },
    ],
    recommendations: [
      { category: 'agrotechnika', title: 'Mulczowanie', justification: 'Ogranicza parowanie', evidence_ids: ['E07'], eco_scheme: null, priority: 2, location: null },
      { category: 'retencja', title: 'Zastawka na rowie', justification: 'Rów 40 m od działki', evidence_ids: ['E05', 'E10'], eco_scheme: 'Retencjonowanie wody', priority: 1, location: null },
    ],
    irrigation: {
      status: 'zalecane', reason: 'Zapas poniżej progu', first_day: '2026-07-02', net_dose_mm: 25, gross_dose_mm: 31, split_into: 2,
      volume_m3: 384, forecast_precip_7d_mm: 3, forecast_etc_7d_mm: 32, forecast_available: true, legal_note: 'Pobór powyżej 5 m³/dobę wymaga zgłoszenia.',
    },
    confidence: [{ section: 'ocena wilgotności', level: 'średnia', reason: 'gleba z SoilGrids' }],
    sources: [
      { name: 'ULDK', url: 'https://uldk.gugik.gov.pl', license: 'GUGiK', retrieved_at: '2026-07-01T10:00:00Z', period_start: null, period_end: null, status: 'ok', note: null },
      { name: 'Sentinel-2', url: 'https://example.org', license: 'CC BY', retrieved_at: '2026-07-01T10:00:00Z', period_start: '2016-01-01', period_end: '2026-06-28', status: 'częściowo', note: 'zachmurzenie' },
    ],
    limitations: [
      { code: 'info1', message: 'Model 30 m', severity: 'info', section: 'teren' },
      { code: 'crit1', message: 'Brak danych radarowych', severity: 'krytyczne', section: 'satelita' },
      { code: 'meteo1', message: 'Luka w danych meteo', severity: 'ostrzeżenie', section: 'meteo' },
    ],
    mock: false,
    ...overrides,
  };
}
