import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Location } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Report } from '../../core/report.model';
import { riskMonthsLabel } from './levels';
import { reportFixture } from './report.fixture';
import { ReportPage } from './report.page';

describe('riskMonthsLabel', () => {
  it('names a contiguous range like the backend', () => {
    expect(riskMonthsLabel(reportFixture().water!.climate.risk_calendar)).toBe('maj–lipiec');
  });
});

describe('ReportPage', () => {
  async function setup(state: { report?: Report } | null, id = 'abc123def456') {
    await TestBed.configureTestingModule({
      imports: [ReportPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    vi.spyOn(TestBed.inject(Location), 'getState').mockReturnValue(state);
    const fixture = TestBed.createComponent(ReportPage);
    fixture.componentRef.setInput('id', id);
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;
    const settle = async () => {
      // czat Kolby w oknie dialogowym pobiera gotowe pytania — bez odpowiedzi whenStable by czekało
      http.match('/api/assistant/questions').forEach((r) => r.flush([]));
      await fixture.whenStable();
      fixture.detectChanges();
    };
    return { http, el, settle };
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
    expect(el.textContent).toContain('Brak oceny');
    expect(el.textContent).toContain('Bez oceny stanu wody nie podajemy zaleceń nawadniania.');
  });

  it('shows mock banner and skips summary, PDF and map for mock reports', async () => {
    const { http, el, settle } = await setup({ report: reportFixture({ mock: true }) });
    http.expectNone('/api/report/abc123def456/summary');
    await settle();
    expect(el.textContent).toContain('Dane przykładowe');
    expect(el.querySelector('a[href$=".pdf"]')).toBeNull();
    expect(el.querySelector('img')).toBeNull();
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
