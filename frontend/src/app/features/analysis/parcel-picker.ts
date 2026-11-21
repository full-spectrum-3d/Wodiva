import { afterNextRender, Component, DestroyRef, effect, ElementRef, inject, input, output, signal, viewChild } from '@angular/core';
import type * as Leaflet from 'leaflet';

import { EGIB_MIN_ZOOM, EGIB_WMS, gugikWms, loadLeaflet, orthoLayer, parcelOutline, prefersReducedMotion } from '../../core/map/leaflet';
import { Parcel } from '../../core/wodiva-api.model';

/** Środek i przybliżenie startowe: cała Polska. */
const POLAND: Leaflet.LatLngTuple = [52.07, 19.48];
const POLAND_ZOOM = 6;
/** Od tego przybliżenia widać granice i numery działek EGiB — wcześniej klik trafia „w ciemno”. */
export const PARCELS_MIN_ZOOM = EGIB_MIN_ZOOM;

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
        <p class="picker-failed">Mapa się nie wczytała. Wpisz numer działki w pole powyżej.</p>
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
    const map = L.map(this.canvas().nativeElement, { center: POLAND, zoom: POLAND_ZOOM });
    this.map = map;
    orthoLayer(L).addTo(map);
    gugikWms(L, EGIB_WMS, 'dzialki,numery_dzialek', PARCELS_MIN_ZOOM).addTo(map);
    L.control.scale({ imperial: false }).addTo(map);
    map.on('zoomend', () => this.zoom.set(map.getZoom()));
    map.on('click', (e: Leaflet.LeafletMouseEvent) => {
      this.pending?.remove();
      // tymczasowy znacznik w miejscu kliknięcia, dopóki backend nie zwróci granicy działki
      this.pending = L.circleMarker(e.latlng, { radius: 6, color: '#1B1F1D', weight: 2, fillColor: '#FFD400', fillOpacity: 1 }).addTo(map);
      this.picked.emit({ lat: e.latlng.lat, lon: e.latlng.lng });
    });
    this.ready.set(true);
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
