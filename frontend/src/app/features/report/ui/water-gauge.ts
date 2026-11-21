import { Component, computed, input } from '@angular/core';

import { LEVEL_CLASS, levelFromAvailable } from '../levels';
import { LevelBadge } from './level-badge';

/**
 * Wodowskaz: zapas wody dostępnej dla roślin 0–100% z progami 30/50% (DESIGN.md §1).
 * percentile_10y to odsetek lat (inna skala niż zapas), więc jest tekstem, nie znacznikiem na podziałce.
 * shortcut: zawsze poziomy (DESIGN.md chce pionowego na desktopie) — zmienić, gdy kolumna boczna raportu będzie gotowa.
 */
@Component({
  selector: 'app-water-gauge',
  imports: [LevelBadge],
  template: `
    <figure>
      <figcaption class="flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <span class="text-display leading-tight font-bold num">{{ rounded() }}%</span>
        <span>zapasu wody dostępnej dla roślin</span>
        <app-level-badge [level]="level()" [label]="levelLabel()" />
      </figcaption>

      <div class="relative mt-5 h-10" aria-hidden="true">
        <div class="absolute inset-0 flex overflow-hidden rounded-sm border-2 border-border-strong">
          <div class="h-full w-[30%] bg-level-high-tint"></div>
          <div class="h-full w-[20%] bg-level-watch-tint"></div>
          <div class="h-full flex-1 bg-level-good-tint"></div>
        </div>
        <div class="absolute inset-y-0 left-0 rounded-l-sm" [class]="fillClass()" [style.width.%]="clamped()"></div>
        <div class="absolute -inset-y-1 left-[30%] w-0.5 bg-text"></div>
        <div class="absolute -inset-y-1 left-[50%] w-0.5 bg-text"></div>
      </div>
      <div class="relative mt-2 h-5 text-xs text-text-muted num" aria-hidden="true">
        <span class="absolute left-0">0%</span>
        <span class="absolute left-[30%] -translate-x-1/2">30%</span>
        <span class="absolute left-[50%] -translate-x-1/2">50%</span>
        <span class="absolute right-0">100%</span>
      </div>

      <p class="mt-3 text-sm text-text-muted">
        Poniżej 30% rośliny cierpią z braku wody, 30–50% to stan podwyższonego ryzyka.
        @if (percentile() != null) {
          Na tle 10 lat: tego dnia gleba była tak samo sucha lub suchsza w {{ percentileRounded() }}% poprzednich lat.
        }
      </p>
    </figure>
  `,
})
export class WaterGauge {
  readonly availablePct = input.required<number>();
  readonly percentile = input<number | null>(null);

  protected readonly rounded = computed(() => Math.round(this.availablePct()));
  protected readonly clamped = computed(() => Math.min(100, Math.max(0, this.availablePct())));
  protected readonly percentileRounded = computed(() => Math.round(this.percentile() ?? 0));
  protected readonly level = computed(() => levelFromAvailable(this.availablePct()));
  protected readonly fillClass = computed(() => LEVEL_CLASS[this.level()].fill);
  protected readonly levelLabel = computed(
    () => ({ good: 'Zapas dobry', watch: 'Zapas niski', high: 'Zapas krytyczny', unknown: 'Brak oceny' })[this.level()],
  );
}
