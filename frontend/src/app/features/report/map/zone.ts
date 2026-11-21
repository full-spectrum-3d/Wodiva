import type { Geometry, Polygon, Position } from 'geojson';

const EARTH_M = 6_371_000;

function outerRings(geometry: Geometry): Position[][] {
  if (geometry.type === 'Polygon') return [geometry.coordinates[0]];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.map((p) => p[0]);
  return [];
}

/** Otoczka wypukła (monotone chain), punkty [lon, lat]. */
function convexHull(points: Position[]): Position[] {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: Position, a: Position, b: Position) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const half = (list: Position[]) => {
    const out: Position[] = [];
    for (const p of list) {
      while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], p) <= 0) out.pop();
      out.push(p);
    }
    return out.slice(0, -1);
  };
  return [...half(pts), ...half([...pts].reverse())];
}

/**
 * Strefa `meters` wokół działki: otoczka wypukła okręgów wokół wierzchołków granicy.
 * shortcut: dla działki wklęsłej strefa jest nieco większa niż dokładny bufor — wystarcza do orientacyjnej
 * strefy 500 m na mapie; dokładny bufor (np. @turf/buffer) kosztowałby ~290 kB kodu.
 */
export function zoneAround(geometry: Geometry, meters = 500, steps = 16): Polygon | null {
  const vertices = outerRings(geometry).flat();
  if (!vertices.length) return null;
  const points: Position[] = [];
  for (const [lon, lat] of vertices) {
    const dLat = (meters / EARTH_M) * (180 / Math.PI);
    const dLon = dLat / Math.cos((lat * Math.PI) / 180);
    for (let i = 0; i < steps; i++) {
      const a = (2 * Math.PI * i) / steps;
      points.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
    }
  }
  const hull = convexHull(points);
  return { type: 'Polygon', coordinates: [[...hull, hull[0]]] };
}
