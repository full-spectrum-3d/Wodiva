import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter, Router } from '@angular/router';

import { AnalysisFormPage, analysisDateRange, toLocalIso } from './analysis-form.page';
import { ParcelPicker } from './parcel-picker';

const CROPS = [
  { code: 'pszenica_ozima', name: 'Pszenica ozima', critical_period: '05-01 – 06-30', critical_label: 'strzelanie w źdźbło' },
  { code: 'kukurydza', name: 'Kukurydza', critical_period: '07-01 – 08-15', critical_label: 'kwitnienie' },
];

describe('analysisDateRange', () => {
  it('spans exactly 10 years back in local time', () => {
    expect(analysisDateRange(new Date(2026, 10, 21))).toEqual({ min: '2016-11-21', max: '2026-11-21' });
  });

  it('rolls 29 February to 1 March like the backend', () => {
    expect(analysisDateRange(new Date(2028, 1, 29)).min).toBe('2018-03-01');
  });

  it('formats without UTC shift', () => {
    expect(toLocalIso(new Date(2026, 0, 1, 0, 30))).toBe('2026-01-01');
  });
});

describe('AnalysisFormPage', () => {
  async function setup() {
    await TestBed.configureTestingModule({
      imports: [AnalysisFormPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    const fixture = TestBed.createComponent(AnalysisFormPage);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne('/api/crops').flush(CROPS);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    const settle = async () => {
      await new Promise((resolve) => setTimeout(resolve)); // akcja submit() to łańcuch Promise poza śledzeniem whenStable
      await fixture.whenStable();
      fixture.detectChanges();
    };
    return { fixture, http, el, settle };
  }

  const button = (el: HTMLElement, text: string) =>
    [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.trim() === text)!;
  const stepTitle = (el: HTMLElement) => el.querySelector('#step-heading')?.textContent?.replace(/\s+/g, ' ').trim();

  /** Przejście kreatora: działka → Dalej → (data domyślna) → Dalej → uprawa → Sprawdź działkę. */
  async function fillWizard(el: HTMLElement, settle: () => Promise<void>, parcelId: string, crop = 'kukurydza') {
    const parcel = el.querySelector<HTMLInputElement>('#parcel-id')!;
    parcel.value = parcelId;
    parcel.dispatchEvent(new Event('input'));
    button(el, 'Dalej').click();
    await settle();
    button(el, 'Dalej').click();
    await settle();
    el.querySelector<HTMLInputElement>(`input[value=${crop}]`)!.click();
    button(el, 'Sprawdź działkę').click();
    await settle();
  }

  function type(input: HTMLInputElement, value: string) {
    input.value = value;
    input.dispatchEvent(new Event('input'));
    input.dispatchEvent(new Event('change'));
  }

  it('renders crop tiles from /api/crops on the third step', async () => {
    const { el, settle } = await setup();
    const parcel = el.querySelector<HTMLInputElement>('#parcel-id')!;
    parcel.value = '141201_1.0001.6509';
    parcel.dispatchEvent(new Event('input'));
    button(el, 'Dalej').click();
    await settle();
    button(el, 'Dalej').click();
    await settle();
    expect(stepTitle(el)).toContain('Uprawa');
    expect(el.querySelectorAll('.crop-tile input[type=radio]').length).toBe(2);
    expect(el.textContent).toContain('Okres krytyczny: kwitnienie');
  });

  it('stays on step 1 with a field error when Dalej is pressed without a parcel', async () => {
    const { el, http, settle } = await setup();
    expect(stepTitle(el)).toContain('Działka');
    button(el, 'Dalej').click();
    await settle();
    expect(stepTitle(el)).toContain('Działka');
    expect(el.querySelector('#parcel-id-error')?.textContent).toContain('Podaj numer działki');
    expect(el.querySelector('#parcel-id')?.getAttribute('aria-invalid')).toBe('true');
    http.expectNone('/api/analyze');
  });

  it('walks the wizard forward and back keeping the values; Enter acts as Dalej', async () => {
    const { el, settle } = await setup();
    const parcel = el.querySelector<HTMLInputElement>('#parcel-id')!;
    parcel.value = '141201_1.0001.6509';
    parcel.dispatchEvent(new Event('input'));
    el.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await settle();
    expect(stepTitle(el)).toContain('Data analizy');
    expect(el.querySelector('[aria-current=step]')?.textContent).toContain('Data analizy');
    button(el, 'Wstecz').click();
    await settle();
    expect(stepTitle(el)).toContain('Działka');
    expect(el.querySelector<HTMLInputElement>('#parcel-id')!.value).toBe('141201_1.0001.6509');
  });

  it('shows an error summary on the last step when no crop is chosen', async () => {
    const { el, http, settle } = await setup();
    const parcel = el.querySelector<HTMLInputElement>('#parcel-id')!;
    parcel.value = '141201_1.0001.6509';
    parcel.dispatchEvent(new Event('input'));
    button(el, 'Dalej').click();
    await settle();
    button(el, 'Dalej').click();
    await settle();
    button(el, 'Sprawdź działkę').click();
    await settle();
    expect(el.querySelector('[role=alert]')?.textContent).toContain('Wybierz uprawę');
    expect(stepTitle(el)).toContain('Uprawa');
    http.expectNone('/api/analyze');
  });

  it('picks the parcel clicked on the map: fills the field and outlines it', async () => {
    const { fixture, el, http, settle } = await setup();
    const picker = fixture.debugElement.query(By.directive(ParcelPicker)).componentInstance as ParcelPicker;
    picker.picked.emit({ lat: 52.18, lon: 21.56 });
    const req = http.expectOne((r) => r.url === '/api/parcel' && r.params.get('lat') === '52.18' && r.params.get('lon') === '21.56');
    const geometry = { type: 'Polygon', coordinates: [[[21.56, 52.18], [21.561, 52.18], [21.561, 52.181], [21.56, 52.18]]] };
    req.flush({ parcel: { id: '141201_1.0001.6509', commune: 'Pionki', region: null, county: null, number: '6509', area_ha: 0.27, is_agricultural: true, geometry_geojson: geometry } });
    await settle();
    expect(el.querySelector<HTMLInputElement>('#parcel-id')!.value).toBe('141201_1.0001.6509');
    expect(el.textContent).toContain('Znaleziono działkę 141201_1.0001.6509');
    expect(picker.parcel()?.geometry_geojson).toEqual(geometry);

    // edycja numeru zdejmuje obrys z mapy
    const field = el.querySelector<HTMLInputElement>('#parcel-id')!;
    field.value = '141201_1.0001.1';
    field.dispatchEvent(new Event('input'));
    await settle();
    expect(picker.parcel()).toBeNull();
  });

  it('looks up the parcel and warns when it is not agricultural', async () => {
    const { el, http, settle } = await setup();
    type(el.querySelector<HTMLInputElement>('#parcel-id')!, '141201_1.0001.6509');
    http.expectOne((r) => r.url === '/api/parcel' && r.params.get('id') === '141201_1.0001.6509').flush({
      parcel: { id: '141201_1.0001.6509', commune: 'Pionki', region: 'Krzewina', county: null, number: '6509', area_ha: 1.2, is_agricultural: false },
    });
    await settle();
    expect(el.textContent).toContain('Znaleziono działkę');
    expect(el.textContent).toContain('bez zaleceń nawadniania');
  });

  it('offers candidates when the parcel is ambiguous', async () => {
    const { el, http, settle } = await setup();
    type(el.querySelector<HTMLInputElement>('#parcel-id')!, 'Krzewina 134');
    http
      .expectOne((r) => r.url === '/api/parcel')
      .flush(
        { detail: { message: 'Znaleziono kilka działek – wybierz właściwą.', candidates: [{ id: '141201_1.0001.134', commune: 'Pionki', region: 'Krzewina', county: null }] } },
        { status: 404, statusText: 'Not Found' },
      );
    await settle();
    expect(el.textContent).toContain('Czy chodziło o:');
    expect(el.textContent).toContain('141201_1.0001.134');
  });

  it('submits a valid form and opens the report with it in navigation state', async () => {
    const { el, http, settle } = await setup();
    await fillWizard(el, settle, '141201_1.0001.6509');
    expect(el.querySelector('app-analysis-progress h1')?.textContent).toContain('Analizuję działkę');
    expect(el.querySelector('form')).toBeNull();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const req = http.expectOne('/api/analyze');
    expect(req.request.body).toEqual({ parcel_id: '141201_1.0001.6509', date: analysisDateRange().max, crop: 'kukurydza' });
    const report = { id: 'abc123', analysis_date: '2026-11-21', crop: 'kukurydza', parcel: { id: '141201_1.0001.6509' } };
    req.flush(report);
    await settle();
    expect(navigate).toHaveBeenCalledWith(['/raport', 'abc123'], { state: { report } });
  });

  it('keeps the form and shows a message when the server fails', async () => {
    const { el, http, settle } = await setup();
    await fillWizard(el, settle, '141201_1.0001.6509');
    http.expectOne('/api/analyze').flush(null, { status: 502, statusText: 'Bad Gateway' });
    await settle();
    expect(el.textContent).toContain('Analiza się nie udała');
    button(el, 'Wstecz').click();
    await settle();
    button(el, 'Wstecz').click();
    await settle();
    expect(el.querySelector<HTMLInputElement>('#parcel-id')!.value).toBe('141201_1.0001.6509');
  });

  it('rejects a parcel number that is too short after trimming', async () => {
    const { el, http, settle } = await setup();
    const parcel = el.querySelector<HTMLInputElement>('#parcel-id')!;
    parcel.value = 'ab ';
    parcel.dispatchEvent(new Event('input'));
    button(el, 'Dalej').click();
    await settle();
    expect(el.querySelector('#parcel-id-error')?.textContent).toContain('Numer działki jest za krótki');
    expect(stepTitle(el)).toContain('Działka');
    http.expectNone('/api/analyze');
  });

  it('ignores a stale parcel lookup that answers after a newer one', async () => {
    const { el, http, settle } = await setup();
    const parcel = el.querySelector<HTMLInputElement>('#parcel-id')!;
    type(parcel, '141201_1.0001.1111');
    const first = http.expectOne((r) => r.params.get('id') === '141201_1.0001.1111');
    type(parcel, '141201_1.0001.2222');
    const second = http.expectOne((r) => r.params.get('id') === '141201_1.0001.2222');
    const p = (id: string) => ({ parcel: { id, commune: null, region: null, county: null, number: null, area_ha: 1, is_agricultural: true } });
    second.flush(p('141201_1.0001.2222'));
    first.flush(p('141201_1.0001.1111'));
    await settle();
    expect(parcel.value).toBe('141201_1.0001.2222');
    expect(el.textContent).toContain('Znaleziono działkę 141201_1.0001.2222');
  });

  it('aborts the analysis and does not navigate when the page is left', async () => {
    const { fixture, el, http, settle } = await setup();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate');
    await fillWizard(el, settle, '141201_1.0001.6509');
    const req = http.expectOne('/api/analyze');
    fixture.destroy();
    await new Promise((resolve) => setTimeout(resolve));
    expect(req.cancelled).toBe(true);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('cancel aborts the request and brings the filled form back', async () => {
    const { el, http, settle } = await setup();
    await fillWizard(el, settle, '141201_1.0001.6509');
    const req = http.expectOne('/api/analyze');
    [...el.querySelectorAll<HTMLButtonElement>('app-analysis-progress button')].find((b) => b.textContent?.includes('Anuluj'))!.click();
    await settle();
    expect(req.cancelled).toBe(true);
    expect(el.querySelector('h1')?.textContent).toContain('Sprawdź wodę');
    expect(el.querySelector('[role=alert]')).toBeNull();
    expect(stepTitle(el)).toContain('Uprawa');
  });
});
