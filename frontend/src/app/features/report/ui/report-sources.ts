import { Component, computed, input } from '@angular/core';

import { Confidence, DataSource, Limitation } from '../../../core/report.model';
import { LEVEL_CLASS, levelFromSeverity, levelFromSource } from '../levels';

const SEVERITY_ORDER: Limitation['severity'][] = ['krytyczne', 'ostrzeżenie', 'info'];
const STATUS_LABEL = { ok: 'aktualne', częściowo: 'częściowe', brak: 'brak' } as const;

/** Sekcja 6: źródła, ograniczenia i pewność — pełnoprawna część raportu (kryterium oceny 25%). */
@Component({
  selector: 'app-report-sources',
  template: `
    <h3 class="text-lg">Skąd są dane</h3>
    <ul class="mt-3 divide-y divide-border border-y border-border">
      @for (s of sources(); track $index) {
        <li class="py-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <a [href]="s.url" target="_blank" rel="noopener" class="font-semibold">{{ s.name }}</a>
            <span class="inline-flex items-center gap-2 text-sm font-semibold">
              <span class="size-2.5 rounded-full" [class]="fill(s)" aria-hidden="true"></span>
              {{ statusLabel[s.status] }}
            </span>
          </div>
          <dl class="mt-1 grid grid-cols-[auto_1fr] gap-x-3 text-sm text-text-muted">
            @if (s.period_start || s.period_end) {
              <dt>Okres</dt><dd class="num">{{ s.period_start ?? '…' }} – {{ s.period_end ?? '…' }}</dd>
            }
            <dt>Pobrano</dt><dd class="num">{{ s.retrieved_at.slice(0, 10) }}</dd>
            <dt>Licencja</dt><dd>{{ s.license }}</dd>
            @if (s.note) {
              <dt>Uwaga</dt><dd>{{ s.note }}</dd>
            }
          </dl>
        </li>
      } @empty {
        <li class="py-3 text-text-muted">Raport nie podaje źródeł.</li>
      }
    </ul>

    <h3 class="mt-8 text-lg">Ograniczenia i niepewność</h3>
    @if (grouped().length) {
      <ul class="mt-3 space-y-2">
        @for (l of grouped(); track l.code + l.message) {
          <li class="border-l-4 bg-surface-sunken p-3" [class]="edge(l)">
            <span class="font-semibold">{{ l.severity === 'info' ? 'Informacja' : l.severity === 'ostrzeżenie' ? 'Ostrzeżenie' : 'Krytyczne' }}:</span>
            {{ l.message }}
            @if (l.section) {
              <span class="text-sm text-text-muted">({{ l.section }})</span>
            }
          </li>
        }
      </ul>
    } @else {
      <p class="mt-2 text-text-muted">Brak zgłoszonych ograniczeń.</p>
    }

    @if (confidence().length) {
      <h3 class="mt-8 text-lg">Pewność wyników</h3>
      <ul class="mt-3 space-y-1">
        @for (c of confidence(); track $index) {
          <li><span class="font-semibold">{{ c.section }}:</span> pewność {{ c.level }} — {{ c.reason }}</li>
        }
      </ul>
    }
  `,
})
export class ReportSources {
  readonly sources = input.required<DataSource[]>();
  readonly limitations = input.required<Limitation[]>();
  readonly confidence = input.required<Confidence[]>();

  protected readonly statusLabel = STATUS_LABEL;
  protected readonly grouped = computed(() =>
    [...this.limitations()].sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)),
  );

  protected fill(s: DataSource): string {
    return s.status === 'ok' ? 'bg-success' : LEVEL_CLASS[levelFromSource(s.status)].fill;
  }

  protected edge(l: Limitation): string {
    return l.severity === 'info' ? 'border-primary' : LEVEL_CLASS[levelFromSeverity(l.severity)].edge;
  }
}
