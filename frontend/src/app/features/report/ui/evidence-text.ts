import { Component, computed, input } from '@angular/core';

import { EvidenceRef } from './evidence-ref';

export interface TextPart {
  text: string;
  /** Ustawione, gdy fragment jest identyfikatorem źródła (np. E05). */
  evidenceId?: string;
}

/** Dzieli tekst na zwykłe fragmenty i identyfikatory E01–E22 (bez HTML — samo dopasowanie wzorca). */
export function splitEvidenceText(text: string): TextPart[] {
  return text
    .split(/(\bE\d{2}\b)/)
    .map((part, i): TextPart => (i % 2 ? { text: part, evidenceId: part } : { text: part }))
    .filter((part) => part.text);
}

/** Tekst, w którym identyfikatory źródeł są przyciskami otwierającymi modal. */
@Component({
  selector: 'app-evidence-text',
  imports: [EvidenceRef],
  template: `@for (part of parts(); track $index) {@if (part.evidenceId) {<app-evidence-ref [id]="part.evidenceId" />} @else {{{ part.text }}}}`,
})
export class EvidenceText {
  readonly text = input.required<string>();
  protected readonly parts = computed(() => splitEvidenceText(this.text()));
}
