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

/**
 * WMS GUGiK: kafelki 512 px (4× mniej zapytań niż 256 px) i pobierane dopiero po zatrzymaniu mapy,
 * nie w trakcie przesuwania i animacji zoomu — usługi GUGiK blokują zbyt częste zapytania.
 */
const WMS_LOAD = { tileSize: 512, updateWhenIdle: true, updateWhenZooming: false } as const;

export function orthoLayer(L: typeof Leaflet): Leaflet.TileLayer.WMS {
  return L.tileLayer.wms(ORTO_WMS, { layers: 'Raster', format: 'image/jpeg', maxZoom: 20, ...WMS_LOAD, attribution: GUGIK_ATTRIBUTION });
}

export function gugikWms(L: typeof Leaflet, url: string, layers: string, minZoom?: number): Leaflet.TileLayer.WMS {
  return L.tileLayer.wms(url, { layers, format: 'image/png', transparent: true, maxZoom: 20, minZoom, ...WMS_LOAD, attribution: GUGIK_ATTRIBUTION });
}

/** Obwódka + żółta granica jako jedna grupa (getBounds → przybliżenie do działki). */
export function parcelOutline(L: typeof Leaflet, geometry: Geometry, pane?: string): Leaflet.FeatureGroup {
  const opts = pane ? { pane } : {};
  return L.featureGroup([
    L.geoJSON(geometry, { ...opts, interactive: false, style: { color: PARCEL_OUTLINE, weight: 7, fill: false } }),
    L.geoJSON(geometry, { ...opts, style: { color: PARCEL_COLOR, weight: 3, fillColor: PARCEL_COLOR, fillOpacity: 0.12 } }),
  ]);
}

/** Przyciski przybliżania z polskimi etykietami (domyślne „Zoom in/out” są po angielsku). */
export function addPolishZoom(L: typeof Leaflet, map: Leaflet.Map): void {
  L.control.zoom({ zoomInTitle: 'Przybliż', zoomOutTitle: 'Oddal' }).addTo(map);
}

export const LAND_USE_LEGEND: [string, string][] = [
  ['R', 'grunty orne'],
  ['Ł', 'łąki'],
  ['Ps', 'pastwiska'],
  ['S', 'sady'],
  ['Br', 'grunty rolne zabudowane'],
  ['W', 'rowy'],
  ['Lz', 'zadrzewienia'],
  ['Ls', 'lasy'],
  ['N', 'nieużytki'],
  ['Wp', 'wody płynące'],
  ['Ws', 'wody stojące'],
  ['B', 'tereny mieszkaniowe'],
  ['Bi', 'inne zabudowane'],
  ['dr', 'drogi'],
];
export const LAND_USE_CLASSES = 'Liczba rzymska przy skrócie to klasa gleby: I najlepsza, VI najsłabsza.';

export function landUseLegendText(): string {
  return LAND_USE_LEGEND.map(([code, name]) => `${code} ${name}`).join(', ');
}

const MAXIMIZED = 'map-maximized';
const ENTER_ICON =
  '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/></svg>';
const EXIT_ICON =
  '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M9 4v5H4M20 9h-5V4M15 20v-5h5M4 15h5v5"/></svg>';
const escapeHandlers = new WeakMap<HTMLElement, (event: KeyboardEvent) => void>();

export function isFullscreen(target: HTMLElement): boolean {
  return document.fullscreenElement === target || target.classList.contains(MAXIMIZED);
}

function setMaximized(target: HTMLElement, on: boolean): void {
  target.classList.toggle(MAXIMIZED, on);
  const previous = escapeHandlers.get(target);
  if (previous) {
    document.removeEventListener('keydown', previous);
    escapeHandlers.delete(target);
  }
  if (on) {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMaximized(target, false);
    };
    escapeHandlers.set(target, handler);
    document.addEventListener('keydown', handler);
  }
  target.dispatchEvent(new Event('fullscreenchange'));
}

export function toggleFullscreen(target: HTMLElement): void {
  if (document.fullscreenElement) {
    void document.exitFullscreen();
    return;
  }
  if (target.classList.contains(MAXIMIZED)) {
    setMaximized(target, false);
    return;
  }
  if (document.fullscreenEnabled && typeof target.requestFullscreen === 'function') {
    const fallback = setTimeout(() => {
      if (document.fullscreenElement !== target) setMaximized(target, true);
    }, 800);
    target.requestFullscreen().then(
      () => {
        clearTimeout(fallback);
        if (target.classList.contains(MAXIMIZED)) setMaximized(target, false);
      },
      () => {
        clearTimeout(fallback);
        if (!target.classList.contains(MAXIMIZED)) setMaximized(target, true);
      },
    );
  } else {
    setMaximized(target, true);
  }
}

export function addFullscreenControl(L: typeof Leaflet, map: Leaflet.Map, target: HTMLElement): void {
  const control = new L.Control({ position: 'topleft' });
  control.onAdd = () => {
    const bar = L.DomUtil.create('div', 'leaflet-bar leaflet-control map-fullscreen');
    const button = L.DomUtil.create('a', '', bar) as HTMLAnchorElement;
    button.href = '#';
    button.setAttribute('role', 'button');
    const sync = () => {
      const full = isFullscreen(target);
      const label = full ? 'Zamknij pełny ekran' : 'Pełny ekran';
      button.title = label;
      button.setAttribute('aria-label', label);
      button.setAttribute('aria-pressed', String(full));
      button.innerHTML = full ? EXIT_ICON : ENTER_ICON;
      setTimeout(() => map.invalidateSize());
    };
    sync();
    target.addEventListener('fullscreenchange', sync);
    L.DomEvent.disableClickPropagation(bar);
    L.DomEvent.on(button, 'click', (event) => {
      L.DomEvent.preventDefault(event);
      toggleFullscreen(target);
    });
    return bar;
  };
  control.addTo(map);
}
