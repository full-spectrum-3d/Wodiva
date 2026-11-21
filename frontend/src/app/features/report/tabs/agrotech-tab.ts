import { Component, computed, input } from '@angular/core';

import { Report } from '../../../core/report.model';
import { RecommendationList } from '../ui/recommendation-list';

/** Zakładka 4: agrotechnika i scenariusze „co by dało…”. */
@Component({
  selector: 'app-agrotech-tab',
  imports: [RecommendationList],
  template: `
    <div class="report-section" [class.step-disabled]="!report().water">
      <h2 id="step-4" class="step-legend"><span class="step-num" aria-hidden="true">4</span> Agrotechnika</h2>
      <div class="mt-4">
        @if (report().water; as w) {
          <app-recommendation-list [items]="items()" />
          @if (w.scenarios.length) {
            <h3 class="mt-6 text-lg">Co by dało…</h3>
            <ul class="mt-2 space-y-3">
              @for (sc of w.scenarios; track sc.code) {
                <li>
                  <p class="font-semibold">{{ sc.name }}</p>
                  <p class="text-text-muted">{{ sc.description }}</p>
                  <p class="mt-1 num">
                    Dni stresu w {{ sc.reference_year }}: {{ sc.stress_days_baseline }} → <strong>{{ sc.stress_days_scenario }}</strong>
                    @if (sc.stress_days_saved > 0) {
                      (o {{ sc.stress_days_saved }} mniej)
                    }
                  </p>
                </li>
              }
            </ul>
          }
        } @else {
          <p>Bez oceny stanu wody nie podajemy zaleceń.</p>
        }
      </div>
    </div>
  `,
})
export class AgrotechTab {
  readonly report = input.required<Report>();

  protected readonly items = computed(() => this.report().recommendations.filter((r) => r.category === 'agrotechnika'));
}
