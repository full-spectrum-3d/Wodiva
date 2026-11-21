import { HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, computed, effect, ElementRef, inject, viewChild } from '@angular/core';

import { EvidenceItem } from '../report.model';
import { EvidenceDialog } from './evidence-dialog';

/** Okno szczegółów źródła z rejestru (GET /api/evidence/{id}). Jedna instancja w app.html. */
@Component({
  selector: 'app-evidence-dialog',
  template: `
    <dialog #dialog class="evidence-dialog" aria-labelledby="evidence-dialog-title" (close)="evidence.closed()">
      <div class="flex items-start justify-between gap-3 border-b border-border pb-3">
        <h2 id="evidence-dialog-title" class="text-xl">Źródło {{ evidence.openId() }}</h2>
        <button type="button" class="btn-secondary" (click)="dialog.close()">Zamknij</button>
      </div>

      <div class="mt-3" aria-live="polite">
        @if (shown(); as item) {
          <p class="font-semibold">{{ item.source }}</p>
          <p class="mt-2 text-text-muted">Do czego: {{ item.purpose }}</p>
        } @else if (notFound()) {
          <p>Nie ma takiej pozycji w rejestrze.</p>
        } @else if (item.error()) {
          <div role="alert" class="border-l-4 border-level-high-fill bg-level-high-tint p-3">
            <p class="text-level-high-text">Nie udało się wczytać opisu źródła {{ evidence.openId() }}.</p>
            <button type="button" class="btn-secondary mt-2" (click)="item.reload()">Spróbuj ponownie</button>
          </div>
        } @else {
          <p class="text-text-muted" role="status">Wczytuję…</p>
        }
      </div>

      <p class="mt-4 text-sm">
        <a href="/api/evidence" target="_blank" rel="noopener">Cały rejestr źródeł (otwiera się w nowej karcie)</a>
      </p>
    </dialog>
  `,
})
export class EvidenceDialogHost {
  protected readonly evidence = inject(EvidenceDialog);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  protected readonly item = httpResource<EvidenceItem>(() => {
    const id = this.evidence.openId();
    return id ? `/api/evidence/${encodeURIComponent(id)}` : undefined;
  });
  protected readonly notFound = computed(() => (this.item.error() as HttpErrorResponse | undefined)?.status === 404);
  // Przy zmianie id zasób może chwilę trzymać poprzednią wartość — pokazujemy tylko pasującą.
  protected readonly shown = computed(() => {
    const value = this.item.hasValue() ? this.item.value() : undefined;
    return value?.id === this.evidence.openId() ? value : undefined;
  });

  constructor() {
    effect(() => {
      const dialog = this.dialog().nativeElement;
      // showModal() na drugim dialogu ląduje w top layer nad otwartym dialogiem Kolby.
      if (this.evidence.openId() && !dialog.open) dialog.showModal();
    });
  }
}
