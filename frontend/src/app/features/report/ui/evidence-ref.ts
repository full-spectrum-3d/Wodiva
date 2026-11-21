import { Component, inject, input } from '@angular/core';

import { EvidenceDialog } from '../../../core/evidence/evidence-dialog';

/** Identyfikator z rejestru źródeł (E01–E22) — przycisk otwierający wspólny modal ze szczegółami. */
@Component({
  selector: 'app-evidence-ref',
  host: { class: 'inline' },
  template: `
    <button type="button" class="link font-semibold" aria-haspopup="dialog" (click)="open($event)">{{ id() }}</button>
  `,
})
export class EvidenceRef {
  readonly id = input.required<string>();
  private readonly dialog = inject(EvidenceDialog);

  protected open(event: Event): void {
    this.dialog.open(this.id(), event.currentTarget as HTMLElement);
  }
}
