import { TestBed } from '@angular/core/testing';

import { AnalysisProgress, SLOW_AFTER_S, STAGES, stageAt } from './analysis-progress';

describe('stageAt', () => {
  it('maps elapsed seconds to the stage that has started', () => {
    expect(stageAt(0)).toBe(0);
    expect(stageAt(8)).toBe(2);
    expect(stageAt(120)).toBe(STAGES.length - 1);
  });
});

describe('AnalysisProgress', () => {
  afterEach(() => vi.useRealTimers());

  async function setup() {
    vi.useFakeTimers();
    await TestBed.configureTestingModule({ imports: [AnalysisProgress] }).compileComponents();
    const fixture = TestBed.createComponent(AnalysisProgress);
    fixture.componentRef.setInput('parcelId', '141201_1.0001.6509');
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('announces only the stage, moves on with time and warns when slow', async () => {
    const { fixture, el } = await setup();
    const status = () => el.querySelector('[role=status]')!.textContent!;
    expect(el.querySelector('h1')?.textContent).toContain('141201_1.0001.6509');
    expect(status()).toContain('Etap: Działka i granice (ULDK)');
    expect(status()).not.toContain('Minęło');

    vi.advanceTimersByTime(10_000);
    fixture.detectChanges();
    expect(status()).toContain('Etap: Zdjęcia satelitarne');
    expect(el.textContent).toContain('Minęło 10 s');
    expect(status()).not.toContain('Trwa dłużej');

    vi.advanceTimersByTime((SLOW_AFTER_S - 10) * 1000);
    fixture.detectChanges();
    expect(status()).toContain('Trwa dłużej niż zwykle');
  });

  it('emits cancel', async () => {
    const { fixture, el } = await setup();
    const cancel = vi.fn();
    fixture.componentInstance.cancel.subscribe(cancel);
    el.querySelector<HTMLButtonElement>('button')!.click();
    expect(cancel).toHaveBeenCalledOnce();
  });
});
