import { Component, computed, input } from '@angular/core';

import { DecadeRisk } from '../../../core/report.model';
import { decadeFreq, Level, LEVEL_CLASS, levelFromDecade, RISK_LABEL, riskMonthsLabel } from '../levels';

const HEIGHT: Record<Level, string> = { good: 'h-1/3', watch: 'h-2/3', high: 'h-full', unknown: 'h-1/3' };

/** Kalendarz ryzyka: 36 dekad w skali poziomów + tekstowe podsumowanie (DESIGN.md §6.3). */
@Component({
  selector: 'app-risk-calendar',
  template: `
    <h3 class="text-lg">Kiedy w roku najczęściej brakuje wody</h3>
    <p class="mt-1">
      @if (monthsLabel(); as months) {
        Najbardziej ryzykowne: <strong>{{ months }}</strong> (w co najmniej połowie z {{ years() }} lat).
      } @else {
        W żadnej dekadzie ryzyko nie wystąpiło w co najmniej połowie z {{ years() }} lat.
      }
    </p>
    <!-- Poziom kodowany kolorem i wysokością słupka (WCAG 1.4.1) + legenda słowna. -->
    <ol class="mt-3 grid h-10 grid-cols-[repeat(36,minmax(0,1fr))] items-end gap-px border-b-2 border-border-strong" aria-label="Ryzyko suszy w kolejnych dekadach roku">
      @for (cell of cells(); track cell.key) {
        <li [class]="cell.fill + ' ' + cell.height" [class.unknown-cell]="cell.level === 'unknown'" [title]="cell.text">
          <span class="visually-hidden">{{ cell.text }}</span>
        </li>
      }
    </ol>
    <div class="mt-1 grid grid-cols-12 text-xs text-text-muted" aria-hidden="true">
      @for (m of monthInitials; track $index) {
        <span class="text-center">{{ m }}</span>
      }
    </div>
    <ul class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label="Legenda">
      @for (l of legend; track l.level) {
        <li class="flex items-center gap-2">
          <span class="inline-block w-3" [class]="l.fill + ' ' + l.height" [class.unknown-cell]="l.level === 'unknown'" aria-hidden="true"></span>
          {{ l.label }}
        </li>
      }
    </ul>
  `,
  styles: `
    .unknown-cell {
      background-image: repeating-linear-gradient(45deg, transparent 0 3px, var(--color-surface) 3px 5px);
    }
  `,
})
export class RiskCalendar {
  readonly calendar = input.required<DecadeRisk[]>();
  readonly years = input.required<number>();

  protected readonly legend = (['good', 'watch', 'high', 'unknown'] as const).map((level) => ({
    level,
    fill: LEVEL_CLASS[level].fill,
    height: HEIGHT[level],
    label: { good: 'rzadko (< 25% lat)', watch: 'czasem (25–49% lat)', high: 'często (≥ 50% lat)', unknown: 'brak danych' }[level],
  }));
  protected readonly monthInitials = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'];
  protected readonly monthsLabel = computed(() => riskMonthsLabel(this.calendar()));
  protected readonly cells = computed(() =>
    this.calendar().map((d) => {
      const level = levelFromDecade(d);
      const freq = decadeFreq(d);
      const share = freq == null ? 'brak danych' : `${Math.round(freq * 100)}% lat`;
      return { key: `${d.month}-${d.decade}`, level, fill: LEVEL_CLASS[level].fill, height: HEIGHT[level], text: `${d.label}: ${RISK_LABEL[level].toLowerCase()} (${share})` };
    }),
  );
}
