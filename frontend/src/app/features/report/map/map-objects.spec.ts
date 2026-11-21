import type { Polygon } from 'geojson';

import { reportFixture } from '../report.fixture';
import { firstSentence, mapObjects, recommendationKey } from './map-objects';
import { endBearing } from './parcel-map';
import { zoneAround } from './zone';

const square: Polygon = {
  type: 'Polygon',
  coordinates: [[[21.0, 52.0], [21.001, 52.0], [21.001, 52.001], [21.0, 52.001], [21.0, 52.0]]],
};

describe('mapObjects', () => {
  const report = reportFixture({
    recommendations: [
      { category: 'retencja', title: 'Zastawka na rowie', justification: 'Rów jest blisko. Drugie zdanie.', evidence_ids: ['E05'], eco_scheme: null, priority: 1, location: { kind: 'zagłębienie', geometry: { type: 'Point', coordinates: [21.0005, 52.0005] } } },
      { category: 'agrotechnika', title: 'Mulcz', justification: 'Bez miejsca.', evidence_ids: [], eco_scheme: null, priority: 2, location: null },
    ],
    terrain: {
      slope_mean_pct: 2, slope_max_pct: 6, tree_cover_buffer_pct: 4,
      depressions: [{ geometry: square, area_m2: 1200, max_depth_m: 0.45, volume_m3: 310, inside_parcel_share: 0.8 }],
      flow_lines: [{ geometry: { type: 'LineString', coordinates: [[21, 52], [21.001, 52]] }, length_m: 140, max_contributing_area_ha: 2.5 }],
    },
    hydro: {
      ditches: [{ type: 'rów melioracyjny', distance_m: 60, width_m: 2.5, mphp_id: '2654', geometry: { type: 'Point', coordinates: [21.002, 52] } }],
      watercourses: [{ type: 'ciek', distance_m: 300 }],
      water_bodies: [{ type: 'staw', distance_m: 420, nearest_point: { lon: 21.004, lat: 52.001 } }],
      groundwater: { wells: [{ place: 'Pionki', lon: 21.1, lat: 51.9, distance_km: 7.3, water_table_depth_m: 3.21, measured_on: '2025-06-30' }, { place: 'Brak', lon: null, lat: null }] },
      edo: null,
    },
  });
  const objects = mapObjects(report);
  const byKind = (k: string) => objects.filter((o) => o.kind === k);

  it('writes popup texts from report numbers (Polish format)', () => {
    expect(byKind('zaglebienie')[0].lines[0]).toBe('Powierzchnia 1200 m², głębokość do 0,5 m, może zatrzymać ok. 310 m³ wody, na działce 80%.');
    expect(byKind('splyw')[0].lines[0]).toBe('Długość 140 m, zbiera wodę z ok. 2,5 ha.');
    expect(byKind('row')[0]).toMatchObject({ label: 'rów melioracyjny', lines: ['60 m od działki, szerokość 2,5 m, MPHP 2654.'] });
    expect(byKind('studnia')[0].lines[0]).toBe('Pionki, 7,3 km, zwierciadło na głębokości 3,21 m (2025-06-30).');
  });

  it('numbers recommendation markers by report order and skips ones without a location', () => {
    const recs = byKind('rekomendacja');
    expect(recs).toHaveLength(1);
    expect(recs[0]).toMatchObject({ key: recommendationKey('Zastawka na rowie'), number: 1, evidence: ['E05'], lines: ['Rów jest blisko.'] });
  });

  it('uses nearest_point when there is no shape and skips objects without any position', () => {
    expect(byKind('zbiornik')[0].geometry).toEqual({ type: 'Point', coordinates: [21.004, 52.001] });
    expect(byKind('ciek')).toHaveLength(0);
    expect(byKind('studnia')).toHaveLength(1);
  });

  it('returns nothing for a report without map data', () => {
    expect(mapObjects(reportFixture({ recommendations: [] }))).toEqual([]);
  });
});

describe('map helpers', () => {
  it('cuts the first sentence', () => {
    expect(firstSentence('Pierwsze zdanie. Drugie.')).toBe('Pierwsze zdanie.');
    expect(firstSentence('Bez kropki')).toBe('Bez kropki');
  });

  it('points the flow arrow along the last segment', () => {
    expect(endBearing({ type: 'LineString', coordinates: [[21, 52], [21.001, 52]] })).toBeCloseTo(0);
    expect(endBearing({ type: 'LineString', coordinates: [[21, 52], [21, 52.001]] })).toBeCloseTo(90);
    expect(endBearing({ type: 'Point', coordinates: [21, 52] })).toBeNull();
  });

  it('builds a closed ring about 500 m around the parcel', () => {
    const ring = zoneAround(square, 500)!.coordinates[0];
    expect(ring[0]).toEqual(ring.at(-1));
    const lats = ring.map((p) => p[1]);
    // 500 m ≈ 0,0045° szerokości
    expect(Math.max(...lats) - 52.001).toBeCloseTo(0.0045, 3);
    expect(52.0 - Math.min(...lats)).toBeCloseTo(0.0045, 3);
    expect(zoneAround({ type: 'Point', coordinates: [21, 52] })).toBeNull();
  });
});
