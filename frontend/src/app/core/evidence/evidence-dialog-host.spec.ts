import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { EvidenceRef } from '../../features/report/ui/evidence-ref';
import { stubDialog } from '../../testing/dialog-stub';
import { EvidenceDialogHost } from './evidence-dialog-host';

@Component({
  imports: [EvidenceRef, EvidenceDialogHost],
  template: `
    <dialog id="kolba"><app-evidence-ref id="E05" /></dialog>
    <app-evidence-ref id="E99" />
    <app-evidence-dialog />
  `,
})
class Harness {}

describe('EvidenceDialogHost', () => {
  beforeEach(() => stubDialog());

  async function setup() {
    await TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }).compileComponents();
    const fixture = TestBed.createComponent(Harness);
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;
    const settle = async () => {
      await new Promise((resolve) => setTimeout(resolve));
      fixture.detectChanges();
    };
    const evidence = el.querySelector<HTMLDialogElement>('app-evidence-dialog dialog')!;
    const kolba = el.querySelector<HTMLDialogElement>('#kolba')!;
    return { http, el, settle, evidence, kolba };
  }

  it('opens a modal over the Kolba dialog with the source, then closes and returns focus to the link', async () => {
    const { http, el, settle, evidence, kolba } = await setup();
    kolba.showModal();
    const trigger = kolba.querySelector('button')!;
    trigger.focus();
    expect(evidence.open).toBe(false);
    http.expectNone('/api/evidence/E05');

    trigger.click();
    await settle();
    expect(evidence.open).toBe(true);
    expect(el.querySelector('#evidence-dialog-title')?.textContent).toContain('Źródło E05');
    expect(evidence.textContent).toContain('Wczytuję…');

    http.expectOne('/api/evidence/E05').flush({ id: 'E05', source: 'European Commission (2015). NWRM guide', purpose: 'oczka, zastoiska' });
    await settle();
    expect(evidence.textContent).toContain('NWRM guide');
    expect(evidence.textContent).toContain('Do czego: oczka, zastoiska');
    const registry = evidence.querySelector('a')!;
    expect(registry.getAttribute('href')).toBe('/api/evidence');
    expect(registry.getAttribute('target')).toBe('_blank');
    expect(registry.textContent).toContain('nowej karcie');

    // Esc/„Zamknij” kończą się zdarzeniem close; Kolba zostaje otwarta, fokus wraca na odnośnik
    evidence.querySelector('button')!.click();
    await settle();
    expect(evidence.open).toBe(false);
    expect(kolba.open).toBe(true);
    expect(document.activeElement).toBe(trigger);
  });

  it('says the source is not in the registry on 404', async () => {
    const { http, settle, evidence, el } = await setup();
    el.querySelectorAll('app-evidence-ref')[1].querySelector('button')!.click();
    await settle();
    http.expectOne('/api/evidence/E99').flush({ detail: 'nie ma' }, { status: 404, statusText: 'Not Found' });
    await settle();
    expect(evidence.textContent).toContain('Nie ma takiej pozycji w rejestrze');
    expect(evidence.querySelector('[role=alert]')).toBeNull();
  });

  it('offers retry on other errors', async () => {
    const { http, settle, evidence, el } = await setup();
    el.querySelectorAll('app-evidence-ref')[1].querySelector('button')!.click();
    await settle();
    http.expectOne('/api/evidence/E99').flush(null, { status: 503, statusText: 'down' });
    await settle();
    expect(evidence.querySelector('[role=alert]')?.textContent).toContain('Nie udało się wczytać opisu źródła E99');

    [...evidence.querySelectorAll('button')].find((b) => b.textContent?.includes('Spróbuj ponownie'))!.click();
    await settle();
    http.expectOne('/api/evidence/E99').flush({ id: 'E99', source: 'Źródło testowe', purpose: 'test' });
    await settle();
    expect(evidence.textContent).toContain('Źródło testowe');
  });
});
