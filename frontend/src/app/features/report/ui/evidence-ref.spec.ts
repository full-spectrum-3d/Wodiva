import { TestBed } from '@angular/core/testing';

import { EvidenceDialog } from '../../../core/evidence/evidence-dialog';
import { EvidenceRef } from './evidence-ref';

describe('EvidenceRef', () => {
  it('is a button that asks the shared dialog to open the source, passing itself as the focus target', async () => {
    await TestBed.configureTestingModule({ imports: [EvidenceRef] }).compileComponents();
    const fixture = TestBed.createComponent(EvidenceRef);
    fixture.componentRef.setInput('id', 'E05');
    fixture.detectChanges();
    const open = vi.spyOn(TestBed.inject(EvidenceDialog), 'open');
    const button = (fixture.nativeElement as HTMLElement).querySelector('button')!;
    expect(button.textContent?.trim()).toBe('E05');
    expect(button.getAttribute('aria-haspopup')).toBe('dialog');
    button.click();
    expect(open).toHaveBeenCalledWith('E05', button);
  });
});
