import { Service, signal } from '@angular/core';

/** „Pokaż na mapie”: lista zaleceń i lista obiektów proszą mapę o pokazanie obiektu po kluczu z map-objects.ts. */
@Service()
export class MapFocus {
  /** `at` pozwala ponownie pokazać ten sam obiekt (inna wartość sygnału). */
  readonly request = signal<{ key: string; at: number } | null>(null);

  show(key: string): void {
    this.request.set({ key, at: Date.now() });
  }
}
