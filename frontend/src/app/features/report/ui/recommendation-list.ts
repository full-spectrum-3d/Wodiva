import { Component, computed, inject, input } from '@angular/core';

import { Recommendation } from '../../../core/report.model';
import { PRIORITY_LABEL } from '../levels';
import { MapFocus } from '../map/map-focus';
import { recommendationKey } from '../map/map-objects';
import { EvidenceRef } from './evidence-ref';
import { EvidenceText } from './evidence-text';

/** Rekomendacje jednej kategorii po priorytecie (DESIGN.md §5 „Rekomendacja”). */
@Component({
  selector: 'app-recommendation-list',
  imports: [EvidenceRef, EvidenceText],
  template: `
    @if (sorted().length) {
      <ol class="space-y-4">
        @for (rec of sorted(); track rec.title) {
          <li class="border-l-4 border-primary pl-4">
            <p class="text-sm font-semibold text-text-muted uppercase">{{ priorityLabel[rec.priority] ?? 'Potem' }}</p>
            <h3 class="mt-1 text-lg">{{ rec.title }}</h3>
            <p class="mt-1"><app-evidence-text [text]="rec.justification" /></p>
            <p class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              @if (rec.evidence_ids.length) {
                <span>
                  Na podstawie:
                  @for (id of rec.evidence_ids; track id; let last = $last) {
                    <app-evidence-ref [id]="id" />{{ last ? '' : ', ' }}
                  }
                </span>
              }
              @if (rec.eco_scheme) {
                <span class="rounded-sm bg-success-tint px-2 py-0.5 font-semibold text-success">Ekoschemat: {{ rec.eco_scheme }}</span>
              }
              @if (rec.location) {
                <button type="button" class="link no-print font-semibold" (click)="showOnMap(rec.title)">Pokaż na mapie</button>
              }
            </p>
          </li>
        }
      </ol>
    } @else {
      <p class="text-text-muted">{{ emptyText() }}</p>
    }
  `,
})
export class RecommendationList {
  readonly items = input.required<Recommendation[]>();
  readonly emptyText = input('Brak zaleceń w tej kategorii dla tej działki.');

  private readonly mapFocus = inject(MapFocus);
  protected readonly priorityLabel = PRIORITY_LABEL;
  protected readonly sorted = computed(() => [...this.items()].sort((a, b) => a.priority - b.priority));

  protected showOnMap(title: string): void {
    this.mapFocus.show(recommendationKey(title));
  }
}
