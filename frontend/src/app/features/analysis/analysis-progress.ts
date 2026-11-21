import { afterNextRender, Component, computed, DestroyRef, ElementRef, inject, input, output, signal, viewChild } from '@angular/core';

/** Backend nie raportuje postępu — etapy przełączają się według typowych czasów (DESIGN.md §6.2). */
export const STAGES = [
  { label: 'Działka i granice (ULDK)', from: 0 },
  { label: 'Pogoda z 10 lat', from: 2 },
  { label: 'Gleba', from: 6 },
  { label: 'Zdjęcia satelitarne', from: 9 },
  { label: 'Teren i cieki', from: 15 },
  { label: 'Ocena i zalecenia', from: 19 },
] as const;

export const SLOW_AFTER_S = 35;

export function stageAt(seconds: number): number {
  return STAGES.filter((s) => seconds >= s.from).length - 1;
}

@Component({
  selector: 'app-analysis-progress',
  template: `
    <section aria-labelledby="progress-heading">
      <h1 id="progress-heading" #heading tabindex="-1" class="text-2xl">
        Analizuję działkę <span class="mt-1 block font-mono text-xl wrap-anywhere">{{ parcelId() }}</span>
      </h1>
      <p class="mt-3 text-text-muted">
        Zwykle trwa 15–25 sekund. <span class="num">Minęło {{ elapsed() }} s.</span>
      </p>

      <div class="mt-8 flex gap-5">
        <div class="gauge" aria-hidden="true">
          <div class="gauge-fill" [style.height.%]="fillPct()"></div>
        </div>
        <ol class="flex flex-1 flex-col-reverse justify-between gap-3">
          @for (stage of stages; track stage.label; let i = $index) {
            <li class="flex min-h-12 items-center gap-3" [class.font-bold]="i === current()" [class.text-text-muted]="i > current()">
              <span class="stage-mark" aria-hidden="true">
                @if (i < current()) {
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                } @else if (i === current()) {
                  <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="6" /></svg>
                } @else {
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5" /></svg>
                }
              </span>
              <span>
                {{ stage.label }}
                <span class="visually-hidden">{{ i < current() ? '— gotowe' : i === current() ? '— w toku' : '— czeka' }}</span>
              </span>
            </li>
          }
        </ol>
      </div>

      <!-- Czytnik ekranu dostaje tylko zmianę etapu i ewentualne opóźnienie, nie każdą sekundę. -->
      <div role="status" aria-live="polite" class="mt-6">
        <p class="visually-hidden">Etap: {{ stages[current()].label }}</p>
        @if (slow()) {
          <p class="rounded-md border-l-4 border-level-watch-fill bg-level-watch-tint p-3 text-level-watch-text">
            Trwa dłużej niż zwykle — pobieramy brakujące lata danych satelitarnych.
          </p>
        }
      </div>

      <button type="button" class="btn-secondary mt-6" (click)="cancel.emit()">Anuluj</button>
    </section>
  `,
  styles: `
    .gauge {
      position: relative;
      flex: none;
      width: 1.25rem;
      border: var(--border-control) solid var(--color-border-strong);
      border-radius: var(--radius-sm);
      background: repeating-linear-gradient(
          to top,
          transparent 0 calc(100% / 6 - 2px),
          var(--color-border-strong) calc(100% / 6 - 2px) calc(100% / 6)
        )
        var(--color-surface);
      overflow: hidden;
    }
    .gauge-fill {
      position: absolute;
      inset-inline: 0;
      bottom: 0;
      background: var(--color-level-good-fill);
      transition: height 600ms var(--ease-out);
    }
    .gauge-fill::before {
      content: '';
      position: absolute;
      inset-inline: 0;
      top: -3px;
      height: 6px;
      border-radius: 50%;
      background: var(--color-level-good-fill);
      animation: wave 1.6s ease-in-out infinite alternate;
    }
    @keyframes wave {
      from { transform: scaleX(0.6) translateY(1px); }
      to { transform: scaleX(1) translateY(-1px); }
    }
    .stage-mark {
      display: inline-flex;
      flex: none;
      width: 1.5rem;
      height: 1.5rem;
      color: var(--color-level-good-text);
    }
  `,
})
export class AnalysisProgress {
  readonly parcelId = input.required<string>();
  readonly cancel = output();

  protected readonly stages = STAGES;
  protected readonly elapsed = signal(0);
  protected readonly current = computed(() => stageAt(this.elapsed()));
  protected readonly fillPct = computed(() => ((this.current() + 1) / STAGES.length) * 100);
  protected readonly slow = computed(() => this.elapsed() >= SLOW_AFTER_S);

  private readonly heading = viewChild.required<ElementRef<HTMLElement>>('heading');

  constructor() {
    const timer = setInterval(() => this.elapsed.update((s) => s + 1), 1000);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
    afterNextRender(() => this.heading().nativeElement.focus());
  }
}
