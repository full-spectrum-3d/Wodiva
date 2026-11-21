import type { Geometry } from 'geojson';
import type * as Leaflet from 'leaflet';

/** Wspólne elementy map (formularz i raport): usługi GUGiK i styl granicy działki. */
export const GUGIK_ATTRIBUTION = 'Ortofotomapa, NMT, EGiB, BDOT10k: © GUGiK';
export const ORTO_WMS = 'https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution';
export const NMT_WMS = 'https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WMS/ShadedRelief';
/** KIEG (EGiB): granice i numery działek, użytki. Rysuje działki dopiero przy małym zakresie mapy (od EGIB_MIN_ZOOM). */
export const EGIB_WMS = 'https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow';
export const EGIB_MIN_ZOOM = 17;
export const BDOT_WMS = 'https://mapy.geoportal.gov.pl/wss/service/pub/guest/kompozycja_BDOT10k_WMS/MapServer/WMSServer';

/** Granica działki: żółta linia 3 px na ciemnej obwódce (widoczna na ortofotomapie i mapie ogólnej). */
export const PARCEL_COLOR = '#FFD400';
export const PARCEL_OUTLINE = '#1B1F1D';

/** Ograniczenie ruchu w systemie (bez matchMedia — np. w testach — traktujemy jak brak ograniczenia). */
export function prefersReducedMotion(): boolean {
  return globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

/** Leaflet ładowany leniwie (osobny chunk); pakiet jest CommonJS, stąd odczyt `default`. */
export async function loadLeaflet(): Promise<typeof Leaflet> {
  const mod = await import('leaflet');
  return ((mod as unknown as { default?: typeof Leaflet }).default ?? mod) as typeof Leaflet;
}

/** Mapa podstawowa (domyślna): OpenStreetMap — nie turystyczna, zimowa, lotnicza ani z ruchem drogowym. */
export function basicLayer(L: typeof Leaflet): Leaflet.TileLayer {
  return L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' });
}

export function orthoLayer(L: typeof Leaflet): Leaflet.TileLayer.WMS {
  return L.tileLayer.wms(ORTO_WMS, { layers: 'Raster', format: 'image/jpeg', maxZoom: 20, attribution: GUGIK_ATTRIBUTION });
}

export function gugikWms(L: typeof Leaflet, url: string, layers: string, minZoom?: number): Leaflet.TileLayer.WMS {
  return L.tileLayer.wms(url, { layers, format: 'image/png', transparent: true, maxZoom: 20, minZoom, attribution: GUGIK_ATTRIBUTION });
}

/** Obwódka + żółta granica jako jedna grupa (getBounds → przybliżenie do działki). */
export function parcelOutline(L: typeof Leaflet, geometry: Geometry, pane?: string): Leaflet.FeatureGroup {
  const opts = pane ? { pane } : {};
  return L.featureGroup([
    L.geoJSON(geometry, { ...opts, interactive: false, style: { color: PARCEL_OUTLINE, weight: 7, fill: false } }),
    L.geoJSON(geometry, { ...opts, style: { color: PARCEL_COLOR, weight: 3, fillColor: PARCEL_COLOR, fillOpacity: 0.12 } }),
  ]);
}
