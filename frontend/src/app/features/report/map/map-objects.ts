import type { Geometry } from 'geojson';

import { Report, WaterObject } from '../../../core/report.model';

export type MapObjectKind = 'zaglebienie' | 'splyw' | 'rekomendacja' | 'row' | 'ciek' | 'zbiornik' | 'studnia';

/** Obiekt z raportu do narysowania na mapie i do tekstowej listy pod nią (dostępność). */
export interface MapObject {
  key: string;
  kind: MapObjectKind;
  /** Nazwa w liście i nagłówek okienka. */
  label: string;
  geometry: Geometry;
  /** Wiersze treści okienka (zwykły tekst — bez HTML). */
  lines: string[];
  /** Numer znacznika rekomendacji (kolejność w raporcie). */
  number?: number;
  /** Identyfikatory źródeł E01–E22 (rekomendacje). */
  evidence?: string[];
  /** Objętość zagłębienia — do odcienia wypełnienia. */
  volume?: number;
}

const fmt = (value: number | null | undefined, digits = 0): string =>
  value == null ? '—' : new Intl.NumberFormat('pl-PL', { maximumFractionDigits: digits }).format(value);

const point = (lon: number, lat: number): Geometry => ({ type: 'Point', coordinates: [lon, lat] });

/** Klucz rekomendacji wspólny dla listy zaleceń i mapy („Pokaż na mapie”). */
export const recommendationKey = (title: string) => `rek:${title}`;

/** Pierwsze zdanie tekstu (uzasadnienie rekomendacji w okienku). */
export function firstSentence(text: string): string {
  const match = /^.*?[.!?](\s|$)/.exec(text);
  return (match ? match[0] : text).trim();
}

function waterObjects(items: WaterObject[] | undefined, kind: 'row' | 'ciek' | 'zbiornik', fallback: string): MapObject[] {
  return (items ?? []).flatMap((w, i) => {
    const geometry = w.geometry ?? (w.nearest_point ? point(w.nearest_point.lon, w.nearest_point.lat) : null);
    if (!geometry) return [];
    // typ jest w tytule okienka — w treści tylko liczby
    const parts = [w.distance_m != null ? `${fmt(w.distance_m)} m od działki` : null];
    if (w.width_m != null) parts.push(`szerokość ${fmt(w.width_m, 1)} m`);
    if (w.mphp_id) parts.push(`MPHP ${w.mphp_id}`);
    return [{ key: `${kind}:${i}`, kind, label: w.type ?? fallback, geometry, lines: [parts.filter(Boolean).join(', ') + '.'] }];
  });
}

/** Wszystkie obiekty mapy z raportu (granica działki rysowana osobno). Treści okienek wg specyfikacji mapy. */
export function mapObjects(report: Report): MapObject[] {
  const objects: MapObject[] = [];

  report.terrain?.depressions.forEach((d, i) =>
    objects.push({
      key: `zaglebienie:${i}`,
      kind: 'zaglebienie',
      label: `Zagłębienie terenu ${i + 1}`,
      geometry: d.geometry,
      volume: d.volume_m3,
      lines: [
        `Powierzchnia ${fmt(d.area_m2)} m², głębokość do ${fmt(d.max_depth_m, 1)} m, może zatrzymać ok. ${fmt(d.volume_m3)} m³ wody` +
          (d.inside_parcel_share != null ? `, na działce ${fmt(d.inside_parcel_share * 100)}%.` : '.'),
      ],
    }),
  );

  report.terrain?.flow_lines.forEach((f, i) =>
    objects.push({
      key: `splyw:${i}`,
      kind: 'splyw',
      label: `Linia spływu ${i + 1}`,
      geometry: f.geometry,
      lines: [`Długość ${fmt(f.length_m)} m, zbiera wodę z ok. ${fmt(f.max_contributing_area_ha, 1)} ha.`],
    }),
  );

  report.recommendations.forEach((r, i) => {
    if (!r.location?.geometry) return;
    objects.push({
      key: recommendationKey(r.title),
      kind: 'rekomendacja',
      label: r.title,
      number: i + 1,
      geometry: r.location.geometry,
      evidence: r.evidence_ids,
      lines: [firstSentence(r.justification)],
    });
  });

  objects.push(
    ...waterObjects(report.hydro?.ditches, 'row', 'Rów'),
    ...waterObjects(report.hydro?.watercourses, 'ciek', 'Ciek'),
    ...waterObjects(report.hydro?.water_bodies, 'zbiornik', 'Zbiornik wodny'),
  );

  report.hydro?.groundwater?.wells?.forEach((w, i) => {
    if (w.lon == null || w.lat == null) return;
    const depth =
      w.water_table_depth_m != null
        ? `zwierciadło na głębokości ${fmt(w.water_table_depth_m, 2)} m${w.measured_on ? ` (${w.measured_on})` : ''}`
        : 'brak pomiaru sprzed daty analizy';
    objects.push({
      key: `studnia:${i}`,
      kind: 'studnia',
      label: `Wody podziemne: ${w.place ?? w.id ?? 'punkt monitoringu'}`,
      geometry: point(w.lon, w.lat),
      lines: [`${w.place ?? 'Punkt PIG-PIB'}, ${fmt(w.distance_km, 1)} km, ${depth}.`],
    });
  });

  return objects;
}
