import { DecimalPipe } from '@angular/common';
import { afterNextRender, Component, computed, DestroyRef, effect, ElementRef, inject, input, signal, viewChild } from '@angular/core';
import type { Geometry, Point } from 'geojson';
import type * as Leaflet from 'leaflet';

import { Report } from '../../../core/report.model';
import { MapFocus } from './map-focus';
import { MapObject, mapObjects } from './map-objects';
import { zoneAround } from './zone';

/** Kolory i wzory z specyfikacji mapy — każdy obiekt ma też inny kształt lub wzór linii. */
const STYLE = {
  parcel: '#FFD400',
  parcelOutline: '#1B1F1D',
  depression: '#1E88E5',
  flow: '#00ACC1',
  water: '#0D47A1',
  zone: '#6B6F68',
} as const;

const GUGIK = 'Ortofotomapa, NMT, EGiB, BDOT10k: © GUGiK';
const POPUP = { minWidth: 220, maxWidth: 300 };
const BDOT_WMS = 'https://mapy.geoportal.gov.pl/wss/service/pub/guest/kompozycja_BDOT10k_WMS/MapServer/WMSServer';
const EGIB_WMS = 'https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow';
const LEGEND_KINDS: Record<MapObject['kind'], string> = {
  zaglebienie: 'Zagłębienie terenu',
  splyw: 'Linia spływu',
  rekomendacja: 'Miejsce z zalecenia',
  row: 'Rów',
  ciek: 'Ciek',
  zbiornik: 'Zbiornik wodny',
  studnia: 'Wody podziemne (PIG-PIB)',
};

/** Kierunek ostatniego odcinka linii (stopnie, 0 = wschód) — do strzałki na końcu linii spływu. */
export function endBearing(geometry: Geometry): number | null {
  const coords =
    geometry.type === 'LineString' ? geometry.coordinates : geometry.type === 'MultiLineString' ? geometry.coordinates.at(-1) : null;
  if (!coords || coords.length < 2) return null;
  const [[x1, y1], [x2, y2]] = coords.slice(-2);
  return (Math.atan2(y2 - y1, (x2 - x1) * Math.cos((y2 * Math.PI) / 180)) * 180) / Math.PI;
}

/** Interaktywna mapa działki (Leaflet). W druku zastępuje ją statyczna mapa /api/report/{id}/map.png. */
@Component({
  selector: 'app-parcel-map',
  imports: [DecimalPipe],
  templateUrl: './parcel-map.html',
})
export class ParcelMap {
  readonly report = input.required<Report>();

  private readonly focus = inject(MapFocus);
  private readonly frame = viewChild.required<ElementRef<HTMLElement>>('frame');
  private readonly canvas = viewChild.required<ElementRef<HTMLElement>>('canvas');

  protected readonly objects = computed(() => mapObjects(this.report()));
  protected readonly ndvi = computed(() => this.report().satellite?.details?.ndvi_overlay ?? null);
  protected readonly ndviGradient = computed(() => `linear-gradient(to right, ${this.ndvi()?.colors.join(', ')})`);
  protected readonly ndviOn = signal(false);
  protected readonly failed = signal(false);
  protected readonly legendKinds = computed(() => [...new Set(this.objects().map((o) => o.kind))].map((k) => ({ kind: k, label: LEGEND_KINDS[k] })));
  protected readonly hasDepressions = computed(() => (this.report().terrain?.depressions.length ?? 0) > 0);
  protected readonly geoportalUrl = computed(
    () => `https://mapy.geoportal.gov.pl/imap/Imgp_2.html?identifyParcel=${encodeURIComponent(this.report().parcel.id)}`,
  );

  private map: Leaflet.Map | null = null;
  private parcelBounds: Leaflet.LatLngBounds | null = null;
  private readonly layers = new Map<string, { layer: Leaflet.Layer; group: Leaflet.LayerGroup }>();

  constructor() {
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      void this.init().catch(() => this.failed.set(true));
    });
    destroyRef.onDestroy(() => this.map?.remove());

    effect(() => {
      const req = this.focus.request();
      if (req) this.show(req.key);
    });
  }

  protected backToParcel(): void {
    if (this.map && this.parcelBounds) this.map.fitBounds(this.parcelBounds, { padding: [24, 24] });
  }

  protected fullscreen(): void {
    const el = this.frame().nativeElement;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen?.();
  }

  protected showOnMap(key: string): void {
    this.focus.show(key);
  }

  private async init(): Promise<void> {
    const mod = await import('leaflet');
    const L = ((mod as unknown as { default?: typeof Leaflet }).default ?? mod) as typeof Leaflet;
    const report = this.report();

    // shortcut: na telefonie przesuwanie jednym palcem wyłączone (przewija stronę), działa szczypanie i pełny ekran;
    // prawdziwe „przesuwanie dwoma palcami” wymaga wtyczki gesture-handling — dodać, jeśli rolnicy zgłoszą potrzebę.
    const map = L.map(this.canvas().nativeElement, { zoomControl: true, attributionControl: true, dragging: !L.Browser.mobile });
    this.map = map;
    this.frame().nativeElement.addEventListener('fullscreenchange', () => {
      const full = document.fullscreenElement === this.frame().nativeElement;
      if (L.Browser.mobile) full ? map.dragging.enable() : map.dragging.disable();
      map.invalidateSize();
    });
    map.createPane('parcel').style.zIndex = '650';
    L.control.scale({ imperial: false }).addTo(map);

    const ortho = L.tileLayer.wms('https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution', {
      layers: 'Raster',
      format: 'image/jpeg',
      maxZoom: 20,
      attribution: GUGIK,
    });
    const bases: Record<string, Leaflet.Layer> = {
      'Ortofotomapa (GUGiK)': ortho,
      'Mapa ogólna (OpenStreetMap)': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap',
      }),
      'Cieniowanie terenu (NMT GUGiK, wolniejsze)': L.tileLayer.wms(
        'https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WMS/ShadedRelief',
        { layers: 'Raster', format: 'image/png', maxZoom: 20, attribution: GUGIK },
      ),
    };
    ortho.addTo(map);

    const wms = (url: string, layers: string, minZoom?: number) =>
      L.tileLayer.wms(url, { layers, format: 'image/png', transparent: true, maxZoom: 20, minZoom, attribution: GUGIK });

    const overlays: Record<string, Leaflet.Layer> = {};
    const group = (name: string, on = true) => {
      const g = L.layerGroup();
      overlays[name] = g;
      if (on) g.addTo(map);
      return g;
    };

    // Kolejność dodawania = kolejność w przełączniku.
    const zone = group('Strefa 500 m wokół działki');
    const groups: Record<MapObject['kind'], Leaflet.LayerGroup> = {
      zaglebienie: group('Zagłębienia terenu'),
      splyw: group('Linie spływu wody'),
      row: group('Najbliższy rów, ciek, zbiornik'),
      ciek: L.layerGroup(),
      zbiornik: L.layerGroup(),
      rekomendacja: group('Miejsca z zaleceń'),
      studnia: group('Wody podziemne (PIG-PIB)'),
    };
    // rów/ciek/zbiornik w jednej pozycji przełącznika
    groups.ciek = groups.row;
    groups.zbiornik = groups.row;

    const ndvi = this.ndvi();
    let ndviLayer: Leaflet.ImageOverlay | null = null;
    if (ndvi) {
      ndviLayer = L.imageOverlay(ndvi.url, ndvi.bounds, { opacity: ndvi.opacity, className: 'map-ndvi' });
      overlays[`Stan roślin NDVI${ndvi.date ? ` (${ndvi.date})` : ''}`] = ndviLayer;
    }
    overlays['Działki sąsiednie (EGiB, od przybliżenia 15)'] = wms(EGIB_WMS, 'dzialki,numery_dzialek', 15);
    overlays['Użytki i klasy gleb (EGiB)'] = wms(EGIB_WMS, 'uzytki,kontury', 15);
    overlays['Rowy, rzeki, kanały (BDOT10k)'] = wms(BDOT_WMS, 'row,rz,rzOk,kan,kanOkr');
    overlays['Wody i mokradła (BDOT10k)'] = wms(BDOT_WMS, 'WPow,Mo,Szu');
    overlays['Lasy i zadrzewienia (BDOT10k)'] = wms(BDOT_WMS, 'TLes,RKr');

    L.control.layers(bases, overlays, { collapsed: true }).addTo(map);
    map.on('overlayadd', (e) => e.layer === ndviLayer && this.ndviOn.set(true));
    map.on('overlayremove', (e) => e.layer === ndviLayer && this.ndviOn.set(false));

    // Granica działki: ciemna obwódka + żółta linia, zawsze na wierzchu.
    const geometry = report.parcel.geometry_geojson;
    if (geometry) {
      L.geoJSON(geometry, { pane: 'parcel', style: { color: STYLE.parcelOutline, weight: 7, fill: false } }).addTo(map);
      const parcel = L.geoJSON(geometry, { pane: 'parcel', style: { color: STYLE.parcel, weight: 3, fillOpacity: 0 } }).addTo(map);
      parcel.bindPopup(this.popup(`Działka ${report.parcel.id}`, [this.parcelLine(report)]), POPUP);
      this.parcelBounds = parcel.getBounds();
      const ring = zoneAround(geometry, 500);
      if (ring) L.geoJSON(ring, { interactive: false, style: { color: STYLE.zone, weight: 2, dashArray: '2 6', fill: false } }).addTo(zone);
      this.backToParcel();
    }

    const volumes = this.objects().filter((o) => o.kind === 'zaglebienie').map((o) => o.volume ?? 0);
    const maxVolume = Math.max(1, ...volumes);
    for (const obj of this.objects()) {
      const layer = this.draw(L, obj, maxVolume);
      layer.addTo(groups[obj.kind]);
      this.layers.set(obj.key, { layer, group: groups[obj.kind] });
    }
  }

  private draw(L: typeof Leaflet, obj: MapObject, maxVolume: number): Leaflet.Layer {
    const popup = this.popup(obj.label, obj.lines, obj.evidence);
    const isPoint = obj.geometry.type === 'Point';
    const [lon, lat] = isPoint ? (obj.geometry as Point).coordinates : [0, 0];

    if (obj.kind === 'rekomendacja') {
      const icon = L.divIcon({ className: 'map-pin', html: `<span>${obj.number}</span>`, iconSize: [30, 30] });
      const at = isPoint ? L.latLng(lat, lon) : L.geoJSON(obj.geometry).getBounds().getCenter();
      return L.marker(at, { icon, title: obj.label, alt: `Zalecenie ${obj.number}: ${obj.label}` }).bindPopup(popup, POPUP);
    }
    if (obj.kind === 'studnia') {
      const icon = L.divIcon({ className: 'map-well', iconSize: [18, 16] });
      return L.marker(L.latLng(lat, lon), { icon, title: obj.label, alt: obj.label }).bindPopup(popup, POPUP);
    }
    if (isPoint) {
      return L.circleMarker(L.latLng(lat, lon), { radius: 7, color: STYLE.water, weight: 3, fillOpacity: 0.3 }).bindPopup(popup, POPUP);
    }
    if (obj.kind === 'zaglebienie') {
      const opacity = 0.25 + 0.45 * ((obj.volume ?? 0) / maxVolume);
      return L.geoJSON(obj.geometry, { style: { color: STYLE.water, weight: 1, fillColor: STYLE.depression, fillOpacity: opacity } }).bindPopup(popup, POPUP);
    }
    if (obj.kind === 'splyw') {
      const line = L.geoJSON(obj.geometry, { style: { color: STYLE.flow, weight: 3, dashArray: '8 6' } });
      const bearing = endBearing(obj.geometry);
      const end = obj.geometry.type === 'LineString' ? obj.geometry.coordinates.at(-1) : null;
      const group = L.featureGroup([line]);
      if (bearing != null && end) {
        // Strzałka w kierunku spływu: obrót ikony o kąt ostatniego odcinka (CSS: 0° = wschód).
        const icon = L.divIcon({ className: 'map-arrow', html: `<span style="transform: rotate(${-bearing}deg)">➤</span>`, iconSize: [18, 18] });
        L.marker(L.latLng(end[1], end[0]), { icon, interactive: false, keyboard: false }).addTo(group);
      }
      return group.bindPopup(popup, POPUP);
    }
    const fillOpacity = obj.kind === 'zbiornik' ? 0.3 : 0;
    return L.geoJSON(obj.geometry, { style: { color: STYLE.water, weight: 2, fillColor: STYLE.water, fillOpacity } }).bindPopup(popup, POPUP);
  }

  /** Treść okienka budowana z DOM i textContent — dane z backendu nigdy nie trafiają jako HTML. */
  private popup(title: string, lines: string[], evidence: string[] = []): HTMLElement {
    const root = document.createElement('div');
    const h = document.createElement('p');
    h.className = 'map-popup__title';
    h.textContent = title;
    root.append(h);
    for (const line of lines) {
      const p = document.createElement('p');
      p.textContent = line;
      root.append(p);
    }
    if (evidence.length) {
      const p = document.createElement('p');
      p.textContent = 'Źródła: ';
      evidence.forEach((id, i) => {
        const a = document.createElement('a');
        a.href = `/api/evidence/${encodeURIComponent(id)}`;
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = id;
        p.append(a, i < evidence.length - 1 ? ', ' : '');
      });
      root.append(p);
    }
    return root;
  }

  private parcelLine(report: Report): string {
    const parts = [report.parcel.id, report.parcel.commune, `${report.parcel.area_ha.toLocaleString('pl-PL')} ha`];
    if (report.water?.crop_name) parts.push(`uprawa ${report.water.crop_name}`);
    return parts.filter(Boolean).join(', ');
  }

  private show(key: string): void {
    const entry = this.layers.get(key);
    const map = this.map;
    if (!entry || !map) return;
    if (!map.hasLayer(entry.group)) entry.group.addTo(map);
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.frame().nativeElement.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' });
    const layer = entry.layer as Leaflet.Layer & { getLatLng?: () => Leaflet.LatLng; getBounds?: () => Leaflet.LatLngBounds };
    if (layer.getLatLng) map.setView(layer.getLatLng(), Math.max(map.getZoom(), 17), { animate: !reduce });
    else if (layer.getBounds) map.fitBounds(layer.getBounds(), { padding: [40, 40], maxZoom: 18, animate: !reduce });
    layer.openPopup?.();
    this.highlight(layer);
  }

  /** Krótkie podświetlenie: grubsza linia albo pulsujący znacznik (klasa CSS). */
  private highlight(layer: Leaflet.Layer): void {
    const el = (layer as Leaflet.Marker).getElement?.();
    if (el) {
      el.classList.add('is-highlighted');
      setTimeout(() => el.classList.remove('is-highlighted'), 2500);
      return;
    }
    const path = layer as Leaflet.GeoJSON;
    path.setStyle?.({ weight: 6 });
    setTimeout(() => path.resetStyle?.(), 2500);
  }
}
