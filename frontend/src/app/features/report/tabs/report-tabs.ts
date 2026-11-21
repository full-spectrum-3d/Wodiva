import { Component, ElementRef, input, output, viewChildren } from '@angular/core';

/** Zakładki raportu w kolejności KOWR: ocena → przyczyny → retencja → agrotechnika → nawadnianie → źródła. */
// \u00AD (miękki dywiz): długie etykiety dzielą się na wąskich kaflach (AGRO-TECHNIKA).
export const REPORT_TABS = [
  { id: 'ocena', label: 'Ocena', icon: 'M12 3c-3 4-6 7.5-6 11a6 6 0 0 0 12 0c0-3.5-3-7-6-11z M7.5 15h9' },
  {
    id: 'przyczyny',
    label: 'Przyczyny',
    icon: 'M12 4.5a3.5 3.5 0 1 1 0 7a3.5 3.5 0 1 1 0-7z M12 1.8v1.4 M5.6 8H4.2 M19.8 8h-1.4 M7.4 3.4l1 1 M16.6 3.4l-1 1 M3 20h18 M7 20l2-3 2 2 2-3 2 2',
  },
  { id: 'retencja', label: 'Retencja', icon: 'M5 20V6 M19 20V6 M5 9h14 M5 13h14 M2 20h20' },
  {
    id: 'agrotechnika',
    label: 'Agro\u00ADtechnika',
    icon: 'M12 21V8 M12 12c-3 0-5-2-5-5 3 0 5 2 5 5z M12 16c3 0 5-2 5-5-3 0-5 2-5 5z M4 21h16',
  },
  {
    id: 'nawadnianie',
    label: 'Nawad\u00ADnianie',
    icon: 'M12 21v-8 M12 13c0-4-3-6.5-7-6.5 M12 13c0-4 3-6.5 7-6.5 M12 13V4 M8 21h8',
  },
  {
    id: 'zrodla',
    label: 'Źródła',
    icon: 'M3 5h6a3 3 0 0 1 3 3v12a2.5 2.5 0 0 0-2.5-2.5H3z M21 5h-6a3 3 0 0 0-3 3v12a2.5 2.5 0 0 1 2.5-2.5H21z',
  },
] as const;

export type ReportTabId = (typeof REPORT_TABS)[number]['id'];

/** Nieznana lub brak wartości w URL → pierwsza zakładka. */
export function tabFromParam(param: string | null | undefined): ReportTabId {
  return REPORT_TABS.find((t) => t.id === param)?.id ?? REPORT_TABS[0].id;
}

export const tabId = (id: ReportTabId) => `tab-${id}`;
export const panelId = (id: ReportTabId) => `panel-${id}`;

/**
 * Kafle-zakładki raportu (styl eRolnik: białe ikony liniowe na ciemnym szkle), wzorzec WAI-ARIA Tabs:
 * roving tabindex, ←/→ (oraz ↑/↓ dla siatki 3×2), Home/End, aktywacja automatyczna.
 */
@Component({
  selector: 'app-report-tabs',
  host: { class: 'block' },
  template: `
    <div role="tablist" aria-label="Części raportu" class="report-tablist" (keydown)="onKeydown($event)">
      @for (t of tabs; track t.id) {
        <button
          #tab
          type="button"
          role="tab"
          class="report-tab"
          [id]="tabId(t.id)"
          [attr.aria-selected]="t.id === active()"
          [attr.aria-controls]="panelId(t.id)"
          [attr.tabindex]="t.id === active() ? 0 : -1"
          (click)="selected.emit(t.id)"
        >
          <span class="report-tab__num" aria-hidden="true">{{ $index + 1 }}</span>
          <svg class="report-tab__icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path [attr.d]="t.icon" /></svg>
          {{ t.label }}
        </button>
      }
    </div>
  `,
})
export class ReportTabs {
  readonly active = input.required<ReportTabId>();
  readonly selected = output<ReportTabId>();

  protected readonly tabs = REPORT_TABS;
  protected readonly tabId = tabId;
  protected readonly panelId = panelId;
  private readonly buttons = viewChildren<ElementRef<HTMLButtonElement>>('tab');

  protected onKeydown(event: KeyboardEvent): void {
    const last = this.tabs.length - 1;
    const current = this.tabs.findIndex((t) => t.id === this.active());
    const target = {
      ArrowRight: current === last ? 0 : current + 1,
      ArrowLeft: current === 0 ? last : current - 1,
      ArrowDown: current === last ? 0 : current + 1,
      ArrowUp: current === 0 ? last : current - 1,
      Home: 0,
      End: last,
    }[event.key];
    if (target === undefined) return;
    event.preventDefault();
    this.buttons()[target].nativeElement.focus();
    this.selected.emit(this.tabs[target].id);
  }
}
