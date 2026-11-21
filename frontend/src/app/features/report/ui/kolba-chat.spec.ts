import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { KolbaChat, modeLabel } from './kolba-chat';

describe('modeLabel', () => {
  it('explains each backend mode', () => {
    expect(modeLabel('AI')).toContain('modelu AI');
    expect(modeLabel('bez AI')).toContain('gotowych pytań');
    expect(modeLabel('bez AI (model niedostępny)')).toContain('niedostępny');
  });
});

describe('KolbaChat', () => {
  async function setup() {
    await TestBed.configureTestingModule({
      imports: [KolbaChat],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    const fixture = TestBed.createComponent(KolbaChat);
    fixture.componentRef.setInput('reportId', 'abc123def456');
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/assistant/questions').flush(['Co zrobić najpierw?', 'Czy nawadniać w tym tygodniu?']);
    const el = fixture.nativeElement as HTMLElement;
    const settle = async () => {
      await new Promise((resolve) => setTimeout(resolve));
      await fixture.whenStable();
      fixture.detectChanges();
    };
    await settle();
    return { http, el, settle };
  }

  it('asks a quick question and shows the answer with sources and mode', async () => {
    const { http, el, settle } = await setup();
    [...el.querySelectorAll<HTMLButtonElement>('button.chip')][0].click();
    await settle();
    expect(el.textContent).toContain('Kolba pisze…');
    const req = http.expectOne('/api/assistant');
    expect(req.request.body).toEqual({ report_id: 'abc123def456', question: 'Co zrobić najpierw?' });
    req.flush({ answer: 'Najpierw zastawka na rowie (E05).', mode: 'AI', evidence: ['E05'] });
    await settle();
    expect(el.querySelector('[role=log]')?.textContent).toContain('Najpierw zastawka');
    expect(el.textContent).toContain('Źródła:');
    expect(el.textContent).toContain('Odpowiedź modelu AI');
    expect(el.querySelector('textarea')).toBeTruthy();
  });

  it('keeps the field but suggests quick questions after an offline answer', async () => {
    const { http, el, settle } = await setup();
    [...el.querySelectorAll<HTMLButtonElement>('button.chip')][1].click();
    await settle();
    http.expectOne('/api/assistant').flush({ answer: 'Nie — dawka za 3 dni.', mode: 'bez AI', evidence: [] });
    await settle();
    // formularz zostaje (fokus nie ucieka), dochodzi podpowiedź
    expect(el.querySelector('textarea')).toBeTruthy();
    expect(el.textContent).toContain('najlepiej wybierz jedno z gotowych pytań');
  });

  it('validates the free-text question and offers retry on error', async () => {
    const { http, el, settle } = await setup();
    el.querySelector<HTMLButtonElement>('button[type=submit]')!.click();
    await settle();
    http.expectNone('/api/assistant');
    expect(el.querySelector('textarea')?.getAttribute('aria-invalid')).toBe('true');
    expect(el.querySelector('#kolba-error')?.textContent).toContain('Wpisz pytanie.');

    const textarea = el.querySelector<HTMLTextAreaElement>('textarea')!;
    textarea.value = 'Czy rów pomoże?';
    textarea.dispatchEvent(new Event('input'));
    el.querySelector<HTMLButtonElement>('button[type=submit]')!.click();
    await settle();
    http.expectOne('/api/assistant').flush(null, { status: 503, statusText: 'down' });
    await settle();
    expect(el.querySelector('[role=alert]')?.textContent).toContain('Nie udało się połączyć');
    expect(textarea.value).toBe('Czy rów pomoże?');

    [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.includes('Spróbuj ponownie'))!.click();
    await settle();
    http.expectOne((r) => r.url === '/api/assistant' && r.body.question === 'Czy rów pomoże?').flush({ answer: 'Tak.', mode: 'AI', evidence: [] });
    await settle();
    expect(el.querySelector('[role=log]')?.textContent).toContain('Tak.');
    expect(el.querySelector('textarea')!.value).toBe('');
  });
});
