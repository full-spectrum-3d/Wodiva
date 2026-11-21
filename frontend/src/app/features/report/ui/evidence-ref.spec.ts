import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { EvidenceRef } from './evidence-ref';

describe('EvidenceRef', () => {
  it('loads the source only when expanded and shows it', async () => {
    await TestBed.configureTestingModule({
      imports: [EvidenceRef],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    const fixture = TestBed.createComponent(EvidenceRef);
    fixture.componentRef.setInput('id', 'E05');
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;
    const button = el.querySelector('button')!;
    http.expectNone('/api/evidence/E05');
    expect(button.getAttribute('aria-expanded')).toBe('false');

    button.click();
    TestBed.tick();
    http.expectOne('/api/evidence/E05').flush({ id: 'E05', source: 'European Commission (2015). NWRM guide', purpose: 'oczka, zastoiska' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(el.querySelector(`#${button.getAttribute('aria-controls')}`)?.textContent).toContain('NWRM guide');
  });
});
