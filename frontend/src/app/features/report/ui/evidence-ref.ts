import { httpResource } from '@angular/common/http';
import { Component, input, signal } from '@angular/core';

import { EvidenceItem } from '../../../core/report.model';

/** Identyfikator z rejestru źródeł (E01–E22) — rozwija się w opis z GET /api/evidence/{id}. */
@Component({
  selector: 'app-evidence-ref',
  host: { class: 'inline' },
  template: `
    <button type="button" class="link font-semibold" [attr.aria-expanded]="open()" [attr.aria-controls]="panelId" (click)="open.set(!open())">
      {{ id() }}
    </button>
    @if (open()) {
      <span [id]="panelId" class="mt-1 block rounded-sm bg-surface-sunken p-2 text-sm">
        @if (item.hasValue()) {
          <span class="block">{{ item.value().source }}</span>
          <span class="block text-text-muted">Do czego: {{ item.value().purpose }}</span>
        } @else if (item.error()) {
          Nie udało się wczytać opisu źródła {{ id() }}.
        } @else {
          Wczytuję…
        }
      </span>
    }
  `,
})
export class EvidenceRef {
  readonly id = input.required<string>();

  private static seq = 0;
  protected readonly panelId = `evidence-${++EvidenceRef.seq}`;
  protected readonly open = signal(false);
  // Pobieramy dopiero po rozwinięciu.
  protected readonly item = httpResource<EvidenceItem>(() =>
    this.open() ? `/api/evidence/${encodeURIComponent(this.id())}` : undefined,
  );
}
