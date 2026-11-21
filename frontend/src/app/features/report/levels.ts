import { DecadeRisk, IrrigationAdvice, Limitation, SourceStatus } from '../../core/report.model';

/** Skala stanu wody z DESIGN.md §2.2 — kolor zawsze z etykietą i ikoną. */
export type Level = 'good' | 'watch' | 'high' | 'unknown';

export const RISK_LABEL: Record<Level, string> = {
  good: 'Ryzyko niskie',
  watch: 'Ryzyko podwyższone',
  high: 'Ryzyko wysokie',
  unknown: 'Brak oceny',
};

export function levelFromRisk(risk: string | null | undefined): Level {
  return risk === 'niska' ? 'good' : risk === 'średnia' ? 'watch' : risk === 'wysoka' ? 'high' : 'unknown';
}

/**
 * Poziom samego zapasu wody (wodowskaz), progi 30% / 50% jak w risk_score w backend/app/land/assessment.py.
 * To NIE jest ocena ryzyka — ta przychodzi z /summary (backend łączy zapas z KBW, SPI, CDI, satelitą).
 */
export function levelFromAvailable(pct: number | null | undefined): Level {
  if (pct == null) return 'unknown';
  return pct >= 50 ? 'good' : pct >= 30 ? 'watch' : 'high';
}

export function levelFromIrrigation(status: IrrigationAdvice['status']): Level {
  return ({ zalecane: 'high', monitoruj: 'watch', niezalecane: 'good', 'nie dotyczy': 'unknown' } as const)[status];
}

export function levelFromSource(status: SourceStatus): Level {
  return ({ ok: 'good', częściowo: 'watch', brak: 'high' } as const)[status];
}

export function levelFromSeverity(severity: Limitation['severity']): Level {
  return ({ info: 'unknown', ostrzeżenie: 'watch', krytyczne: 'high' } as const)[severity];
}

/** RISK_FREQ = 0.5 jak w backend/app/land/recommend/context.py; pasmo 0.25 tylko do koloru komórki. */
export const RISK_FREQ = 0.5;

export function decadeFreq(d: DecadeRisk): number | null {
  if (d.stress_freq == null && d.kbw_deficit_freq == null) return null;
  return Math.max(d.stress_freq ?? 0, d.kbw_deficit_freq ?? 0);
}

export function levelFromDecade(d: DecadeRisk): Level {
  const f = decadeFreq(d);
  if (f == null) return 'unknown';
  return f >= RISK_FREQ ? 'high' : f >= 0.25 ? 'watch' : 'good';
}

const MONTHS = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień'];

/** Jak months_label w backend/app/land/recommend/rules.py. */
export function riskMonthsLabel(calendar: DecadeRisk[]): string | null {
  const months = [...new Set(calendar.filter((d) => (decadeFreq(d) ?? 0) >= RISK_FREQ).map((d) => d.month))].sort((a, b) => a - b);
  if (!months.length) return null;
  const contiguous = months.length >= 3 && months.every((m, i) => i === 0 || m === months[i - 1] + 1);
  return contiguous ? `${MONTHS[months[0] - 1]}–${MONTHS[months.at(-1)! - 1]}` : months.map((m) => MONTHS[m - 1]).join(', ');
}

export const PRIORITY_LABEL: Record<number, string> = { 1: 'Najpierw', 2: 'Potem', 3: 'Warto rozważyć' };

/** Pełne nazwy klas — Tailwind nie wykrywa klas sklejanych w locie. */
export const LEVEL_CLASS: Record<Level, { badge: string; fill: string; edge: string }> = {
  good: { badge: 'bg-level-good-tint text-level-good-text', fill: 'bg-level-good-fill', edge: 'border-level-good-fill' },
  watch: { badge: 'bg-level-watch-tint text-level-watch-text', fill: 'bg-level-watch-fill', edge: 'border-level-watch-fill' },
  high: { badge: 'bg-level-high-tint text-level-high-text', fill: 'bg-level-high-fill', edge: 'border-level-high-fill' },
  unknown: { badge: 'bg-level-unknown-tint text-level-unknown-text', fill: 'bg-level-unknown-fill', edge: 'border-level-unknown-fill' },
};
