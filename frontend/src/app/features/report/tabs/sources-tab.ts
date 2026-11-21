import { Component, input } from '@angular/core';

import { Report } from '../../../core/report.model';
import { ReportSources } from '../ui/report-sources';

/** Zakładka 6: źródła danych, ograniczenia i pewność. */
@Component({
  selector: 'app-sources-tab',
  imports: [ReportSources],
  template: `
    <div class="report-section">
      <h2 id="step-6" class="step-legend"><span class="step-num" aria-hidden="true">6</span> Źródła danych i ograniczenia</h2>
      <div class="mt-4">
        <app-report-sources [sources]="report().sources" [limitations]="report().limitations" [confidence]="report().confidence" />
      </div>
    </div>
  `,
})
export class SourcesTab {
  readonly report = input.required<Report>();
}
