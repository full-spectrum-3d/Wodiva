import { TestBed } from '@angular/core/testing';

import { EvidenceText, splitEvidenceText } from './evidence-text';

describe('splitEvidenceText', () => {
  it('splits plain text and evidence ids', () => {
    expect(splitEvidenceText('Najpierw zastawka (E05).')).toEqual([
      { text: 'Najpierw zastawka (' },
      { text: 'E05', evidenceId: 'E05' },
      { text: ').' },
    ]);
  });

  it('finds several ids and ignores lookalikes', () => {
    const parts = splitEvidenceText('E07 i E10, ale nie XE05, E5 ani E123');
    expect(parts.filter((p) => p.evidenceId).map((p) => p.evidenceId)).toEqual(['E07', 'E10']);
  });

  it('returns a single part for text without ids', () => {
    expect(splitEvidenceText('Bez źródeł.')).toEqual([{ text: 'Bez źródeł.' }]);
  });
});

describe('EvidenceText', () => {
  it('renders ids as buttons and the rest as text, never as HTML', async () => {
    await TestBed.configureTestingModule({ imports: [EvidenceText] }).compileComponents();
    const fixture = TestBed.createComponent(EvidenceText);
    fixture.componentRef.setInput('text', '<b>Zastawka</b> (E05) oraz E10.');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect([...el.querySelectorAll('button')].map((b) => b.textContent?.trim())).toEqual(['E05', 'E10']);
    expect(el.querySelector('b')).toBeNull();
    expect(el.textContent).toContain('<b>Zastawka</b> (E05) oraz E10.');
  });
});
