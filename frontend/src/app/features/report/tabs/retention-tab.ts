import { Component, computed, input } from '@angular/core';

import { Report } from '../../../core/report.model';
import { RecommendationList } from '../ui/recommendation-list';

/** Zakładka 3: zatrzymanie wody (retencja). */
@Component({
  selector: 'app-retention-tab',
  imports: [RecommendationList],
  template: `
    <div class="report-section" [class.step-disabled]="!report().water">
      <h2 id="step-3" class="step-legend"><span class="step-num" aria-hidden="true">3</span> Zatrzymanie wody (retencja)</h2>
      <div class="mt-4">
        @if (report().water) {
          <app-recommendation-list [items]="items()" />
        } @else {
          <p>Bez oceny stanu wody nie podajemy zaleceń.</p>
        }
      </div>
    </div>
  `,
})
export class RetentionTab {
  readonly report = input.required<Report>();

  protected readonly items = computed(() => this.report().recommendations.filter((r) => r.category === 'retencja'));
}
