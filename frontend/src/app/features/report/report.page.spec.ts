import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Location } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import { Report } from '../../core/report.model';
import { riskMonthsLabel } from './levels';
import { stubDialog } from '../../testing/dialog-stub';
import { reportFixture } from './report.fixture';
import { ReportPage } from './report.page';

/** Widoczna etykieta kafla: bez numeru (aria-hidden) i miękkiego dywizu. */
const tabLabel = (t: Element | null) => (t?.textContent ?? '').replace(/^\s*\d+/, '').replace(/\u00AD/g, '').trim();

describe('riskMonthsLabel', () => {
  it('names a contiguous range like the backend', () => {
    expect(riskMonthsLabel(reportFixture().water!.climate.risk_calendar)).toBe('maj–lipiec');
  });
});

describe('ReportPage', () => {
  beforeEach(() => stubDialog());

  async function setup(state: { report?: Report } | null, id = 'abc123def456', inputs: Record<string, string> = {}) {
    await TestBed.configureTestingModule({
      imports: [ReportPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    vi.spyOn(TestBed.inject(Location), 'getState').mockReturnValue(state);
    const fixture = TestBed.createComponent(ReportPage);
    fixture.componentRef.setInput('id', id);
    Object.entries(inputs).forEach(([name, value]) => fixture.componentRef.setInput(name, value));
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;
    const settle = async () => {
      // czat Kolby w oknie dialogowym pobiera gotowe pytania — bez odpowiedzi whenStable by czekało
      http.match('/api/assistant/questions').forEach((r) => r.flush([]));
      await fixture.whenStable();
      fixture.detectChanges();
    };
    return { http, el, settle, fixture };
  }

  it('renders the report from navigation state in KOWR order with the summary headline', async () => {
    const { http, el, settle } = await setup({ report: reportFixture() });
    http.expectNone('/api/report/abc123def456');
    http.expectOne('/api/report/abc123def456/summary').flush({
      report_id: 'abc123def456', status: 'ok', risk_level: 'wysoka', headline: 'Na działce występuje wysokie ryzyko suszy rolniczej.', findings: [],
    });
    await settle();
    const headings = [...el.querySelectorAll('h2[id^=step-]')].map((h) => h.textContent!.replace(/\s+/g, ' ').trim());
    expect(headings).toEqual(['1 Ocena stanu wody', '2 Przyczyny', '3 Zatrzymanie wody (retencja)', '4 Agrotechnika', '5 Nawadnianie', '6 Źródła danych i ograniczenia']);
    expect(el.textContent).toContain('wysokie ryzyko suszy');
    expect(el.textContent).toContain('Ryzyko wysokie');
    expect(el.textContent).toContain('28%');
    expect(el.textContent).toContain('Najbardziej ryzykowne: maj–lipiec');
    expect(el.textContent).toContain('Luka w danych meteo');
    expect(el.textContent).toContain('Ekoschemat: Retencjonowanie wody');
    expect(el.querySelector('a[href="/api/report/abc123def456.pdf"]')).toBeTruthy();
    // mapa interaktywna obok zakładek (widoczna w każdej z nich) + statyczna mapa do druku
    expect(el.querySelector('aside [role=region][aria-label="Mapa działki"]')).toBeTruthy();
    expect(el.querySelector('aside img.print-only')?.getAttribute('src')).toBe('/api/report/abc123def456/map.png');
    const causes = [...el.querySelectorAll('#step-2 ~ ol > li p.font-semibold')].map((p) => p.textContent);
    expect(causes).toEqual(['1. Mało deszczu', '2. Wysokie parowanie']);
  });

  it('fetches the report when there is no navigation state', async () => {
    const { http, el, settle } = await setup(null);
    http.expectOne('/api/report/abc123def456').flush(reportFixture());
    await new Promise((resolve) => setTimeout(resolve)); // nie whenStable — ono czeka też na /summary, które dopiero ma wyjść
    TestBed.tick();
    http.expectOne('/api/report/abc123def456/summary').flush(null, { status: 500, statusText: 'err' });
    await settle();
    expect(el.querySelector('h1')?.textContent).toContain('141201_1.0001.6509');
    // ryzyka nie zgadujemy z available_pct — bez /summary jest jawny błąd z ponowieniem
    expect(el.textContent).not.toContain('Ryzyko wysokie');
    expect(el.textContent).toContain('Nie udało się wczytać oceny ryzyka');
    expect(el.textContent).toContain('Susza rolnicza wg KBW');
  });

  it('keeps steps 2–5 visible but explains there are no recommendations without an assessment', async () => {
    const { http, el, settle } = await setup({ report: reportFixture({ water: null, irrigation: null }) });
    http.expectOne('/api/report/abc123def456/summary').flush({ report_id: 'x', status: 'brak', risk_level: null, headline: '', findings: [] });
    await settle();
    expect(el.querySelectorAll('h2[id^=step-]').length).toBe(6);
    expect(el.querySelectorAll('.step-disabled').length).toBe(4);
    expect(el.querySelectorAll('[role=tab]').length).toBe(6);
    expect(el.textContent).toContain('Brak oceny');
    expect(el.textContent).toContain('Bez oceny stanu wody nie podajemy zaleceń nawadniania.');
  });

  it('uses Report.summary without asking /summary', async () => {
    const summary = { status: 'ok', risk_level: 'średnia' as const, headline: 'Podwyższone ryzyko suszy.', findings: ['KBW poniżej progu.'] };
    const { http, el, settle } = await setup({ report: reportFixture({ summary }) });
    http.expectNone('/api/report/abc123def456/summary');
    await settle();
    expect(el.textContent).toContain('Podwyższone ryzyko suszy.');
    expect(el.textContent).toContain('Ryzyko podwyższone');
    expect(el.textContent).toContain('KBW poniżej progu.');
  });

  it('treats a mock report like a saved one, with a banner', async () => {
    const summary = { status: 'ok', risk_level: 'niska' as const, headline: 'Brak oznak suszy.', findings: [] };
    const { el, settle } = await setup({ report: reportFixture({ mock: true, summary }) });
    await settle();
    expect(el.textContent).toContain('Dane przykładowe');
    expect(el.textContent).toContain('Brak oznak suszy.');
    expect(el.querySelector('a[href="/api/report/abc123def456.pdf"]')).toBeTruthy();
    expect(el.querySelector('img')).toBeTruthy();
    expect(el.querySelector('dialog.kolba-dialog app-kolba-chat')).toBeTruthy();
  });

  it('shows tabs in KOWR order, Ocena first, with exactly one visible panel', async () => {
    const { el, settle } = await setup({ report: reportFixture({ summary: { status: 'ok', risk_level: 'niska', headline: 'x', findings: [] } }) });
    await settle();
    const tabs = [...el.querySelectorAll<HTMLElement>('[role=tab]')];
    expect(tabs.map(tabLabel)).toEqual(['Ocena', 'Przyczyny', 'Retencja', 'Agrotechnika', 'Nawadnianie', 'Źródła']);
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    const panels = [...el.querySelectorAll<HTMLElement>('[role=tabpanel]')];
    expect(panels.filter((p) => !p.hidden).map((p) => p.id)).toEqual(['panel-ocena']);
    // każda zakładka wskazuje swój panel, panel wskazuje zakładkę
    tabs.forEach((t, i) => {
      expect(t.getAttribute('aria-controls')).toBe(panels[i].id);
      expect(panels[i].getAttribute('aria-labelledby')).toBe(t.id);
    });
    // nagłówek raportu zostaje nad zakładkami
    expect(el.querySelector('h1')!.compareDocumentPosition(el.querySelector('[role=tablist]')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('opens the tab from the zakladka query param and ignores unknown values', async () => {
    const summary = { status: 'ok', risk_level: 'niska' as const, headline: 'x', findings: [] };
    const first = await setup({ report: reportFixture({ summary }) }, 'abc123def456', { zakladka: 'nawadnianie' });
    await first.settle();
    expect(tabLabel(first.el.querySelector('[role=tab][aria-selected=true]'))).toBe('Nawadnianie');
    expect(first.el.querySelector<HTMLElement>('#panel-nawadnianie')!.hidden).toBe(false);
    expect(first.el.querySelector<HTMLElement>('#panel-ocena')!.hidden).toBe(true);

    first.fixture.componentRef.setInput('zakladka', 'nie-ma-takiej');
    first.fixture.detectChanges();
    expect(first.el.querySelector<HTMLElement>('#panel-ocena')!.hidden).toBe(false);
  });

  it('switches the tab on click and writes it to the URL without adding history', async () => {
    const summary = { status: 'ok', risk_level: 'niska' as const, headline: 'x', findings: [] };
    const { el, settle, fixture } = await setup({ report: reportFixture({ summary }) });
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    await settle();
    el.querySelector<HTMLElement>('#tab-zrodla')!.click();
    fixture.detectChanges();
    expect(el.querySelector<HTMLElement>('#panel-zrodla')!.hidden).toBe(false);
    expect(el.querySelector<HTMLElement>('#panel-ocena')!.hidden).toBe(true);
    expect(navigate).toHaveBeenCalledWith([], { queryParams: { zakladka: 'zrodla' }, queryParamsHandling: 'merge', replaceUrl: true });
  });

  it('opens the Kolba dialog from the corner button and via openKolba()', async () => {
    const summary = { status: 'ok', risk_level: 'niska' as const, headline: 'x', findings: [] };
    const { el, settle, fixture } = await setup({ report: reportFixture({ summary }) });
    await settle();
    const dialog = el.querySelector<HTMLDialogElement>('dialog.kolba-dialog')!;
    const triggers = el.querySelectorAll('button.kolba-trigger');
    expect(triggers).toHaveLength(1);
    expect(dialog.open).toBe(false);
    (triggers[0] as HTMLButtonElement).click();
    expect(dialog.open).toBe(true);
    dialog.close();
    fixture.componentInstance.openKolba();
    expect(dialog.open).toBe(true);
  });

  it('turns ids inside recommendation text and cause evidence into buttons', async () => {
    const report = reportFixture({
      causes: [{ code: 'opad', label: 'Mało deszczu', contribution_mm: 46, rank: 1, evidence: 'Opad 28% normy (E03)' }],
    });
    report.recommendations[1].justification = 'Rów 40 m od działki, zastawka (E05).';
    const { el, settle } = await setup({ report: { ...report, summary: { status: 'ok', risk_level: 'niska', headline: 'x', findings: [] } } });
    await settle();
    const text = (selector: string) => [...el.querySelectorAll(selector)].map((b) => b.textContent?.trim());
    expect(text('#panel-przyczyny li button')).toEqual(['E03']);
    expect(text('#panel-retencja li button')).toEqual(['E05', 'E05', 'E10']);
  });

  it('offers retry when the report cannot be loaded for reasons other than 404', async () => {
    const { http, el, settle } = await setup(null);
    http.expectOne('/api/report/abc123def456').flush(null, { status: 503, statusText: 'down' });
    await settle();
    expect(el.querySelector('h1')?.textContent).toContain('Nie udało się wczytać raportu');
    [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.includes('Spróbuj ponownie'))!.click();
    TestBed.tick();
    http.expectOne('/api/report/abc123def456');
  });

  it('says the report is gone on 404', async () => {
    const { http, el, settle } = await setup(null, 'ffffffffffff');
    http.expectOne('/api/report/ffffffffffff').flush({ detail: 'Nie ma takiego raportu.' }, { status: 404, statusText: 'Not Found' });
    await settle();
    expect(el.querySelector('h1')?.textContent).toContain('nie jest już dostępny');
  });
});
