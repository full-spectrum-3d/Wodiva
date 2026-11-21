import { Component, computed, input } from '@angular/core';

import { Level, LEVEL_CLASS, RISK_LABEL } from '../levels';

/** Znacznik poziomu: tło tint, tekst, ikona kształtu + słowo (DESIGN.md §2.2, §5). */
@Component({
  selector: 'app-level-badge',
  host: { class: 'inline-flex' },
  template: `
    <span
      class="inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-sm font-semibold"
      [class]="classes[level()].badge"
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2">
        @switch (level()) {
          @case ('good') {
            <path d="M12 3c3.5 4.5 6 8 6 11a6 6 0 0 1-12 0c0-3 2.5-6.5 6-11z" fill="currentColor" />
          }
          @case ('watch') {
            <path d="M12 3c3.5 4.5 6 8 6 11a6 6 0 0 1-12 0c0-3 2.5-6.5 6-11z" /><path d="M8 14h8" />
          }
          @case ('high') {
            <path d="M3 20h18M5 20l3-6 3 3 2-5 3 4 3-6" />
          }
          @default {
            <circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17.5v.01" />
          }
        }
      </svg>
      {{ text() }}
    </span>
  `,
})
export class LevelBadge {
  readonly level = input.required<Level>();
  readonly label = input<string>();
  protected readonly classes = LEVEL_CLASS;
  protected readonly text = computed(() => this.label() ?? RISK_LABEL[this.level()]);
}
