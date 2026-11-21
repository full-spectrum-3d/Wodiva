import { httpResource } from '@angular/common/http';
import { Component, computed, inject, input, signal } from '@angular/core';
import { form, FormField, maxLength, readonly, validate } from '@angular/forms/signals';

import { WodivaApi } from '../../../core/wodiva-api';
import { ApiError, AssistantAnswer } from '../../../core/wodiva-api.model';
import { EvidenceRef } from './evidence-ref';

const MAX_LENGTH = 500;

interface Exchange {
  question: string;
  answer: AssistantAnswer;
}

export function modeLabel(mode: string): string {
  if (mode === 'AI') return 'Odpowiedź modelu AI na podstawie raportu';
  if (mode.includes('niedostępny')) return 'Model AI chwilowo niedostępny — odpowiedź z gotowych pytań';
  return 'Odpowiedź z gotowych pytań (bez modelu AI)';
}

/** Asystent Kolba (DESIGN.md §6.4) — odpowiada tylko z raportu; liczby pochodzą z backendu, nie z modelu. */
@Component({
  selector: 'app-kolba-chat',
  imports: [FormField, EvidenceRef],
  template: `
    <p class="text-sm text-text-muted">Kolba odpowiada tylko na podstawie tego raportu. Nie liczy nowych wyników.</p>

    <ol class="mt-4 space-y-4" role="log" aria-label="Rozmowa z Kolbą">
      @for (x of history(); track $index) {
        <li>
          <p class="font-semibold">{{ x.question }}</p>
          <p class="mt-1 rounded-md bg-surface-sunken p-3 whitespace-pre-line">{{ x.answer.answer }}</p>
          @if (x.answer.evidence.length) {
            <p class="mt-1 text-sm">
              Źródła:
              @for (id of x.answer.evidence; track id; let last = $last) {
                <app-evidence-ref [id]="id" />{{ last ? '' : ', ' }}
              }
            </p>
          }
          <p class="mt-1 text-xs text-text-muted">{{ modeLabel(x.answer.mode) }}</p>
        </li>
      }
    </ol>

    <div aria-live="polite" class="mt-3">
      @if (sending()) {
        <p class="text-text-muted">Kolba pisze…</p>
      }
    </div>

    @if (error(); as message) {
      <div role="alert" class="mt-3 border-l-4 border-level-high-fill bg-level-high-tint p-3">
        <p class="text-level-high-text">{{ message }}</p>
        <button type="button" class="btn-secondary mt-2" (click)="retry()">Spróbuj ponownie</button>
      </div>
    }

    @if (questions.hasValue()) {
      <ul class="mt-4 flex flex-wrap gap-2" aria-label="Gotowe pytania">
        @for (q of questions.value(); track q) {
          <li>
            <button type="button" class="chip" [attr.aria-disabled]="sending()" (click)="ask(q)">{{ q }}</button>
          </li>
        }
      </ul>
    }

    @if (offline()) {
      <p class="mt-4 text-sm text-text-muted">Model AI nie jest dostępny — najlepiej wybierz jedno z gotowych pytań.</p>
    }
    <!-- Formularz zostaje także w trybie bez AI: usunięcie go zgubiłoby fokus (WCAG 2.4.3). -->
    <form class="mt-4" novalidate (submit)="onSubmit($event)">
        <label for="kolba-question" class="font-semibold">Twoje pytanie</label>
        <textarea
          id="kolba-question"
          class="field mt-1 min-h-24"
          rows="3"
          [formField]="question.text"
          [attr.aria-invalid]="question.text().touched() && question.text().invalid()"
          aria-describedby="kolba-count kolba-error"
        ></textarea>
        <div id="kolba-error">
          @if (question.text().touched() && question.text().invalid()) {
            <p class="field-error">{{ question.text().errors()[0].message }}</p>
          }
        </div>
        <div class="mt-1 flex items-center justify-between gap-3">
          <p id="kolba-count" class="text-sm text-text-muted num" [class.text-level-high-text]="length() > maxLength">
            {{ length() }} / {{ maxLength }} znaków
          </p>
          <button type="submit" class="btn-primary" [attr.aria-disabled]="sending()">Wyślij</button>
        </div>
      </form>
  `,
  styles: `
    .chip {
      min-height: var(--tap-min);
      padding: var(--space-2) var(--space-3);
      border: var(--border-control) solid var(--color-primary);
      border-radius: var(--radius-md);
      color: var(--color-primary);
      font-weight: var(--weight-semibold);
      text-align: start;
      cursor: pointer;
    }
    @media (hover: hover) {
      .chip:hover {
        background: var(--color-primary-tint);
      }
    }
  `,
})
export class KolbaChat {
  readonly reportId = input.required<string>();

  private readonly api = inject(WodivaApi);
  protected readonly questions = httpResource<string[]>(() => '/api/assistant/questions');
  protected readonly maxLength = MAX_LENGTH;
  protected readonly modeLabel = modeLabel;

  private readonly model = signal({ text: '' });
  protected readonly question = form(this.model, (p) => {
    validate(p.text, ({ value }) => (value().trim() ? undefined : { kind: 'required', message: 'Wpisz pytanie.' }));
    maxLength(p.text, MAX_LENGTH, { message: `Pytanie może mieć najwyżej ${MAX_LENGTH} znaków.` });
    readonly(p.text, () => this.sending());
  });
  protected readonly length = computed(() => this.model().text.length);

  protected readonly history = signal<Exchange[]>([]);
  protected readonly sending = signal(false);
  protected readonly error = signal<string | null>(null);
  /** Po pierwszej odpowiedzi „bez AI” wiadomo, że backend nie ma klucza — zostają tylko gotowe pytania. */
  protected readonly offline = computed(() => this.history().some((x) => x.answer.mode === 'bez AI'));
  private lastQuestion = '';

  protected onSubmit(event: Event): void {
    event.preventDefault();
    this.question.text().markAsTouched();
    const text = this.model().text.trim();
    if (this.question().invalid() || !text) return;
    void this.ask(text);
  }

  protected retry(): void {
    void this.ask(this.lastQuestion);
  }

  protected async ask(question: string): Promise<boolean> {
    if (this.sending()) return false;
    this.lastQuestion = question;
    this.sending.set(true);
    this.error.set(null);
    try {
      const answer = await this.api.askKolba(this.reportId(), question);
      this.history.update((h) => [...h, { question, answer }]);
      // Czyścimy pole, gdy odpowiedź dotyczy wpisanego pytania (także po „Spróbuj ponownie”).
      if (this.model().text.trim() === question) this.model.set({ text: '' });
      return true;
    } catch (err) {
      this.error.set((err as ApiError).message);
      return false;
    } finally {
      this.sending.set(false);
    }
  }
}
