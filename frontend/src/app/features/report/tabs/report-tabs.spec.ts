import { TestBed } from '@angular/core/testing';

import { panelId, ReportTabs, tabFromParam } from './report-tabs';

/** Widoczna etykieta kafla: bez numeru (aria-hidden) i miękkiego dywizu. */
const tabLabel = (t: Element | null) => (t?.textContent ?? '').replace(/^\s*\d+/, '').replace(/\u00AD/g, '').trim();

describe('tabFromParam', () => {
  it('falls back to the first tab for missing or unknown values', () => {
    expect(tabFromParam(undefined)).toBe('ocena');
    expect(tabFromParam('cokolwiek')).toBe('ocena');
    expect(tabFromParam('nawadnianie')).toBe('nawadnianie');
  });
});

describe('ReportTabs', () => {
  async function setup(active = 'ocena') {
    await TestBed.configureTestingModule({ imports: [ReportTabs] }).compileComponents();
    const fixture = TestBed.createComponent(ReportTabs);
    fixture.componentRef.setInput('active', active);
    fixture.detectChanges();
    const selected: string[] = [];
    fixture.componentInstance.selected.subscribe((id) => selected.push(id));
    const el = fixture.nativeElement as HTMLElement;
    const tabs = [...el.querySelectorAll<HTMLButtonElement>('[role=tab]')];
    /** Naciska klawisz na aktywnej zakładce i przesuwa `active` tak, jak zrobi to strona. */
    const press = (key: string) => {
      const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
      tabs.find((t) => t.getAttribute('aria-selected') === 'true')!.dispatchEvent(event);
      fixture.componentRef.setInput('active', selected.at(-1));
      fixture.detectChanges();
      return event;
    };
    return { el, tabs, selected, press };
  }

  it('exposes the WAI-ARIA tab pattern with roving tabindex', async () => {
    const { el, tabs } = await setup('retencja');
    expect(el.querySelector('[role=tablist]')?.getAttribute('aria-label')).toBeTruthy();
    expect(tabs.map(tabLabel)).toEqual(['Ocena', 'Przyczyny', 'Retencja', 'Agrotechnika', 'Nawadnianie', 'Źródła']);
    expect(tabs.map((t) => t.getAttribute('aria-selected'))).toEqual(['false', 'false', 'true', 'false', 'false', 'false']);
    expect(tabs.map((t) => t.getAttribute('tabindex'))).toEqual(['-1', '-1', '0', '-1', '-1', '-1']);
    expect(tabs[2].getAttribute('aria-controls')).toBe(panelId('retencja'));
  });

  it('activates and focuses with arrows, wrapping around, and with Home/End', async () => {
    const { tabs, selected, press } = await setup();
    expect(press('ArrowRight').defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(tabs[1]);
    press('ArrowLeft');
    press('ArrowLeft'); // z pierwszej zakładki na ostatnią
    expect(selected).toEqual(['przyczyny', 'ocena', 'zrodla']);
    expect(document.activeElement).toBe(tabs[5]);
    press('ArrowRight'); // z ostatniej na pierwszą
    press('End');
    press('Home');
    expect(selected.slice(3)).toEqual(['ocena', 'zrodla', 'ocena']);
  });

  it('ignores other keys and selects on click', async () => {
    const { tabs, selected, press } = await setup();
    expect(press('a').defaultPrevented).toBe(false);
    expect(selected).toEqual([]);
    tabs[4].click();
    expect(selected).toEqual(['nawadnianie']);
  });
});
