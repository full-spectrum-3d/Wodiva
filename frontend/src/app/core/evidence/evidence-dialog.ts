import { Service, signal } from '@angular/core';

/**
 * Jeden współdzielony modal źródła (E01–E22). Odnośniki wołają `open()`, okno hostuje `EvidenceDialogHost`.
 * Zapamiętany wyzwalacz dostaje fokus z powrotem po zamknięciu — także gdy okno leży nad dialogiem Kolby.
 */
@Service()
export class EvidenceDialog {
  /** Id pozycji pokazywanej w oknie; null = okno zamknięte. */
  readonly openId = signal<string | null>(null);
  private trigger: HTMLElement | null = null;

  open(id: string, trigger: HTMLElement | null): void {
    this.trigger = trigger;
    this.openId.set(id);
  }

  /** Wołane przez host po zdarzeniu `close` (Esc, „Zamknij”). */
  closed(): void {
    this.openId.set(null);
    if (this.trigger?.isConnected) this.trigger.focus();
    this.trigger = null;
  }
}
