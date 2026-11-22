import { afterNextRender, Component, DestroyRef, effect, ElementRef, inject, input, output, signal, viewChild } from '@angular/core';
import type * as Leaflet from 'leaflet';

import { addPolishZoom, basicLayer, EGIB_MIN_ZOOM, EGIB_WMS, gugikWms, loadLeaflet, NMT_WMS, orthoLayer, parcelOutline, prefersReducedMotion } from '../../core/map/leaflet';
import { Parcel } from '../../core/wodiva-api.model';

/** Środek i przybliżenie startowe: cała Polska. */
const POLAND: Leaflet.LatLngTuple = [52.07, 19.48];
const POLAND_ZOOM = 6;
/** Od tego przybliżenia widać granice i numery działek EGiB — wcześniej klik trafia „w ciemno”. */
export const PARCELS_MIN_ZOOM = EGIB_MIN_ZOOM;
/** Widok wokół użytkownika: ok. 100 km w każdą stronę od jego lokalizacji. */
export const AROUND_USER_M = 100_000;
/** Wybrany rodzaj mapy — wygoda jednej przeglądarki, nie stan do synchronizacji. */
const BASE_KEY = 'wodiva.map.base';

const BASES = {
  'Mapa podstawowa': basicLayer,
  'Zdjęcia lotnicze (ortofotomapa GUGiK)': orthoLayer,
  'Ukształtowanie terenu (NMT GUGiK)': (L: typeof Leaflet) => gugikWms(L, NMT_WMS, 'Raster'),
} as const;
type BaseName = keyof typeof BASES;

function savedBase(): BaseName {
  try {
    const name = localStorage.getItem(BASE_KEY);
    return name && name in BASES ? (name as BaseName) : 'Mapa podstawowa';
  } catch {
    return 'Mapa podstawowa';
  }
}

export interface PickedPoint {
  lat: number;
  lon: number;
}

/**
 * Mapa w formularzu: kliknięcie wskazuje działkę (punkt → GET /api/parcel?lat&lon w stronie formularza),
 * znaleziona działka jest obrysowana i przybliżona. Alternatywa dla pola z numerem, nie jedyna droga.
 */
@Component({
  selector: 'app-parcel-picker',
  template: `
    <p id="picker-help" class="text-sm text-text-muted">
      Przybliż mapę do swojego pola i kliknij w działkę — numer wpisze się sam.
      @if (zoom() < minZoom) {
        <span class="font-semibold">Granice działek pojawią się po przybliżeniu.</span>
      }
    </p>
    <div class="picker-frame mt-2">
      <div #canvas class="map-canvas" role="region" aria-label="Mapa do wyboru działki" aria-describedby="picker-help"></div>
      @if (failed()) {
        <p class="picker-failed" role="status">Mapa się nie wczytała. Wpisz numer działki w pole powyżej.</p>
      }
    </div>
  `,
})
export class ParcelPicker {
  /** Działka do obrysowania (z wyszukiwania po numerze, lokalizacji albo kliknięcia). */
  readonly parcel = input<Parcel | null>(null);
  readonly picked = output<PickedPoint>();

  protected readonly minZoom = PARCELS_MIN_ZOOM;
  protected readonly zoom = signal(POLAND_ZOOM);
  protected readonly failed = signal(false);

  private readonly canvas = viewChild.required<ElementRef<HTMLElement>>('canvas');
  private L: typeof Leaflet | null = null;
  private map: Leaflet.Map | null = null;
  private outline: Leaflet.FeatureGroup | null = null;
  private pending: Leaflet.CircleMarker | null = null;
  private readonly ready = signal(false);

  constructor() {
    afterNextRender(() => void this.init().catch(() => this.failed.set(true)));
    inject(DestroyRef).onDestroy(() => this.map?.remove());

    // Nowa działka → obrys + przybliżenie; brak działki (edycja pola) → czyszczenie obrysu.
    effect(() => {
      const parcel = this.parcel();
      if (this.ready()) this.showParcel(parcel);
    });
  }

  private async init(): Promise<void> {
    const L = await loadLeaflet();
    this.L = L;
    const map = L.map(this.canvas().nativeElement, { center: POLAND, zoom: POLAND_ZOOM, zoomControl: false });
    addPolishZoom(L, map);
    this.map = map;
    // Rodzaj mapy: domyślnie podstawowa; zmiana w ustawieniach mapy (przycisk w prawym górnym rogu).
    const bases: Record<BaseName, Leaflet.Layer> = {
      'Mapa podstawowa': BASES['Mapa podstawowa'](L),
      'Zdjęcia lotnicze (ortofotomapa GUGiK)': BASES['Zdjęcia lotnicze (ortofotomapa GUGiK)'](L),
      'Ukształtowanie terenu (NMT GUGiK)': BASES['Ukształtowanie terenu (NMT GUGiK)'](L),
    };
    bases[savedBase()].addTo(map);
    const parcels = gugikWms(L, EGIB_WMS, 'dzialki,numery_dzialek', PARCELS_MIN_ZOOM).addTo(map);
    const landUse = gugikWms(L, EGIB_WMS, 'uzytki,kontury', PARCELS_MIN_ZOOM);
    const settings = L.control
      .layers(
        bases,
        {
          [`Granice i numery działek (od przybliżenia ${PARCELS_MIN_ZOOM})`]: parcels,
          [`Użytki: R grunty orne, Ł łąki, Ps pastwiska (od przybliżenia ${PARCELS_MIN_ZOOM})`]: landUse,
        },
        { collapsed: true },
      )
      .addTo(map);
    const toggle = settings.getContainer()?.querySelector<HTMLElement>('.leaflet-control-layers-toggle');
    toggle?.setAttribute('aria-label', 'Ustawienia mapy: rodzaj mapy i granice działek');
    toggle?.setAttribute('title', 'Ustawienia mapy');
    map.on('baselayerchange', (e: Leaflet.LayersControlEvent) => {
      try {
        localStorage.setItem(BASE_KEY, e.name);
      } catch {
        // bez dostępu do pamięci przeglądarki wybór obowiązuje tylko do odświeżenia
      }
    });
    L.control.scale({ imperial: false }).addTo(map);
    this.centerOnUser(L, map);
    map.on('zoomend', () => this.zoom.set(map.getZoom()));
    // Mapa bywa ukrywana (telefon: kroki 2–3) i zmienia rozmiar (pełna wysokość na komputerze) — Leaflet musi to wiedzieć.
    if (typeof ResizeObserver !== 'undefined') {
      const resize = new ResizeObserver(() => map.invalidateSize());
      resize.observe(this.canvas().nativeElement);
      map.on('unload', () => resize.disconnect());
    }
    map.on('click', (e: Leaflet.LeafletMouseEvent) => {
      this.pending?.remove();
      // tymczasowy znacznik w miejscu kliknięcia, dopóki backend nie zwróci granicy działki
      this.pending = L.circleMarker(e.latlng, { radius: 6, color: '#1B1F1D', weight: 2, fillColor: '#FFD400', fillOpacity: 1 }).addTo(map);
      this.picked.emit({ lat: e.latlng.lat, lon: e.latlng.lng });
    });
    this.ready.set(true);
  }

  /**
   * Start: okolica użytkownika (±100 km). Bez zgody na lokalizację albo bez niej w przeglądarce zostaje cała Polska.
   * Nie przesuwamy mapy, jeśli w międzyczasie wybrano już działkę.
   */
  private centerOnUser(L: typeof Leaflet, map: Leaflet.Map): void {
    navigator.geolocation?.getCurrentPosition(
      ({ coords }) => {
        if (this.outline) return;
        map.fitBounds(L.latLng(coords.latitude, coords.longitude).toBounds(2 * AROUND_USER_M), { animate: !prefersReducedMotion() });
      },
      () => undefined,
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 10 * 60_000 },
    );
  }

  private showParcel(parcel: Parcel | null): void {
    const L = this.L;
    const map = this.map;
    if (!L || !map) return;
    this.outline?.remove();
    this.outline = null;
    if (!parcel?.geometry_geojson) return;
    this.pending?.remove();
    this.pending = null;
    this.outline = parcelOutline(L, parcel.geometry_geojson).addTo(map);
    const reduce = prefersReducedMotion();
    map.fitBounds(this.outline.getBounds(), { padding: [32, 32], maxZoom: 18, animate: !reduce });
  }
}
