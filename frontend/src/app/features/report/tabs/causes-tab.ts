import { DecimalPipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';

import { Report } from '../../../core/report.model';
import { EvidenceText } from '../ui/evidence-text';

/** Zakładka 2: przyczyny niedoboru wody (bez oceny — wyjaśnienie zamiast listy). */
@Component({
  selector: 'app-causes-tab',
  imports: [DecimalPipe, EvidenceText],
  template: `
    <div class="report-section" [class.step-disabled]="!report().water">
      <h2 id="step-2" class="step-legend"><span class="step-num" aria-hidden="true">2</span> Przyczyny</h2>
      @if (!report().water) {
        <p class="mt-3">Bez oceny stanu wody nie wskazujemy przyczyn.</p>
      } @else if (causes().length) {
        <ol class="mt-4 space-y-4">
          @for (c of causes(); track c.code) {
            <li>
              <p class="font-semibold">{{ c.rank }}. {{ c.label }}</p>
              @if (c.contribution_mm != null) {
                <div class="mt-1 flex items-center gap-3">
                  <div class="h-3 flex-1 rounded-sm bg-surface-sunken" aria-hidden="true">
                    <div class="h-full rounded-sm bg-level-watch-fill" [style.width.%]="(c.contribution_mm / maxContribution()) * 100"></div>
                  </div>
                  <span class="w-20 text-right text-sm num">{{ c.contribution_mm | number: '1.0-0' }} mm</span>
                </div>
              }
              <p class="mt-1 text-text-muted"><app-evidence-text [text]="c.evidence" /></p>
            </li>
          }
        </ol>
      } @else {
        <p class="mt-3 text-text-muted">Analiza nie wskazała wyraźnych przyczyn niedoboru wody.</p>
      }
    </div>
  `,
})
export class CausesTab {
  readonly report = input.required<Report>();

  protected readonly causes = computed(() => [...this.report().causes].sort((a, b) => a.rank - b.rank));
  protected readonly maxContribution = computed(() => Math.max(1, ...this.causes().map((c) => c.contribution_mm ?? 0)));
}
