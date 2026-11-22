import { DecimalPipe } from '@angular/common';
import { httpResource } from '@angular/common/http';
import { afterNextRender, Component, computed, DestroyRef, ElementRef, inject, Injector, signal, viewChild } from '@angular/core';
import { form, FormField, required, submit, validate } from '@angular/forms/signals';
import { ActivatedRoute, Router } from '@angular/router';

import { WodivaApi } from '../../core/wodiva-api';
import { AddressQuery, ApiError, Crop, Parcel, ParcelCandidate, RegionQuery } from '../../core/wodiva-api.model';
import { AnalysisProgress } from './analysis-progress';
import { ParcelPicker, PickedPoint } from './parcel-picker';

const ANALYSIS_YEARS = 10;

type FocusTarget = 'summary' | 'form' | 'error' | 'parcel';

/** Kroki kreatora (lewa część strony głównej); mapa wyboru działki jest w prawej części. */
export const WIZARD_STEPS = [
  { n: 1, label: 'Działka' },
  { n: 2, label: 'Data analizy' },
  { n: 3, label: 'Uprawa' },
] as const;
export type WizardStep = (typeof WIZARD_STEPS)[number]['n'];

export type SearchMode = 'id' | 'adres' | 'obreb';
export const SEARCH_MODES: { id: SearchMode; label: string }[] = [
  { id: 'id', label: 'Numer działki' },
  { id: 'adres', label: 'Adres' },
  { id: 'obreb', label: 'Gmina i obręb' },
];

type ParcelLookup =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'found'; parcel: Parcel }
  | { state: 'error'; message: string; candidates: ParcelCandidate[] };

/** YYYY-MM-DD w strefie użytkownika (toISOString przesuwa datę do UTC). */
export function toLocalIso(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Zakres dat jak w backendzie (validate_analysis_date): dziś − 10 lat … dziś; 29.02 → 1.03. */
export function analysisDateRange(today = new Date()): { min: string; max: string } {
  const earliest = new Date(today.getFullYear() - ANALYSIS_YEARS, today.getMonth(), today.getDate());
  return { min: toLocalIso(earliest), max: toLocalIso(today) };
}

export function nonAgriculturalReason(parcel: Parcel): string | null {
  if (parcel.is_agricultural === false) {
    return 'To nie jest działka rolna. Wybierz działkę rolną albo wyłącz „Tylko działki rolne”.';
  }
  if (parcel.is_agricultural == null && parcel.land_use_checked) {
    return 'Ewidencja nie podaje użytku tej działki, więc nie wiemy, czy to grunt rolny. Wybierz inną działkę albo wyłącz „Tylko działki rolne”.';
  }
  return null;
}

@Component({
  selector: 'app-analysis-form-page',
  imports: [FormField, AnalysisProgress, DecimalPipe, ParcelPicker],
  templateUrl: './analysis-form.page.html',
})
export class AnalysisFormPage {
  private readonly api = inject(WodivaApi);
  private readonly injector = inject(Injector);
  private readonly router = inject(Router);
  protected readonly mock = inject(ActivatedRoute).snapshot.queryParamMap.get('mock') === 'true';

  protected readonly dates = analysisDateRange();
  protected readonly crops = httpResource<Crop[]>(() => '/api/crops');

  private readonly model = signal({ parcelId: '', date: this.dates.max, crop: '' });
  protected readonly onlyAgricultural = signal(true);
  protected readonly analysis = form(this.model, (p) => {
    // Po trim(), bo tak wysyłamy do backendu (AnalyzeRequest.parcel_id: 3–80 znaków).
    validate(p.parcelId, ({ value }) => {
      const v = value().trim();
      if (!v) return { kind: 'required', message: 'Podaj numer działki, wyszukaj adres albo kliknij działkę na mapie.' };
      if (v.length < 3) return { kind: 'minLength', message: 'Numer działki jest za krótki.' };
      if (v.length > 80) return { kind: 'maxLength', message: 'Numer działki jest za długi.' };
      const found = this.lookup?.();
      if (this.onlyAgricultural() && found?.state === 'found' && found.parcel.id === v) {
        const reason = nonAgriculturalReason(found.parcel);
        if (reason) return { kind: 'nonAgricultural', message: reason };
      }
      return undefined;
    });
    required(p.date, { message: 'Wybierz datę analizy.' });
    validate(p.date, ({ value }) => {
      const v = value();
      return v && (v < this.dates.min || v > this.dates.max)
        ? { kind: 'range', message: `Wybierz dzień od ${this.dates.min} do ${this.dates.max}.` }
        : undefined;
    });
    required(p.crop, { message: 'Wybierz uprawę.' });
  });

  protected readonly lookup = signal<ParcelLookup>({ state: 'idle' });
  /** Działka obrysowana na mapie wyboru — ta sama, którą pokazuje karta „Znaleziono działkę”. */
  protected readonly foundParcel = computed(() => {
    const l = this.lookup();
    return l.state === 'found' ? l.parcel : null;
  });
  protected readonly steps = WIZARD_STEPS;
  protected readonly searchModes = SEARCH_MODES;
  protected readonly searchMode = signal<SearchMode>('id');
  protected readonly address = signal<AddressQuery>({ miejscowosc: '', ulica: '', numer: '', gmina: '' });
  protected readonly region = signal<RegionQuery>({ gmina: '', obreb: '', numer: '' });
  protected readonly step = signal<WizardStep>(1);
  protected readonly locating = signal(false);
  protected readonly showSummary = signal(false);
  protected readonly serverError = signal<string | null>(null);

  private readonly summary = viewChild<ElementRef<HTMLElement>>('summary');
  private readonly formHeading = viewChild<ElementRef<HTMLElement>>('formHeading');
  private readonly stepHeading = viewChild<ElementRef<HTMLElement>>('stepHeading');
  private readonly errorAlert = viewChild<ElementRef<HTMLElement>>('errorAlert');
  private lastLookedUp = '';
  private lookupSeq = 0;
  private abort: AbortController | null = null;
  private focusTarget: FocusTarget | null = null;
  private destroyed = false;

  constructor() {
    // Wyjście z ekranu (np. Wstecz) przerywa analizę — inaczej odpowiedź przekierowałaby na raport.
    inject(DestroyRef).onDestroy(() => {
      this.destroyed = true;
      this.abort?.abort();
    });
  }

  protected agriculturalLabel(parcel: Parcel): string {
    const classes = [...new Set((parcel.land_use ?? []).map((u) => `${u.code}${u.soil_class ? ' ' + u.soil_class : ''}`))];
    const suffix = classes.length ? ` (${classes.slice(0, 5).join(', ')})` : '';
    if (parcel.is_agricultural === true) return `grunt rolny${suffix}`;
    if (parcel.is_agricultural === false) return `grunt nierolny${suffix}`;
    return parcel.land_use_checked ? 'brak danych o użytku w EGiB' : 'EGiB nie odpowiedział, użytek nieznany';
  }

  protected setOnlyAgricultural(event: Event): void {
    this.onlyAgricultural.set((event.target as HTMLInputElement).checked);
  }

  protected setAddress(key: keyof AddressQuery, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.address.update((a) => ({ ...a, [key]: value }));
  }

  protected setRegion(key: keyof RegionQuery, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.region.update((r) => ({ ...r, [key]: value }));
  }

  protected searchAddress(event?: Event): void {
    event?.preventDefault();
    const a = this.address();
    const query = { miejscowosc: a.miejscowosc.trim(), ulica: a.ulica.trim(), numer: a.numer.trim(), gmina: a.gmina.trim() };
    if (query.miejscowosc.length < 2 || !query.numer) {
      this.lookup.set({ state: 'error', message: 'Podaj miejscowość i numer domu.', candidates: [] });
      return;
    }
    this.runLookup(this.api.findParcelByAddress(query));
  }

  protected searchRegion(event?: Event): void {
    event?.preventDefault();
    const r = this.region();
    const query = { gmina: r.gmina.trim(), obreb: r.obreb.trim(), numer: r.numer.trim() };
    if (query.gmina.length < 2 || query.obreb.length < 2 || !query.numer) {
      this.lookup.set({ state: 'error', message: 'Podaj gminę, obręb i numer działki.', candidates: [] });
      return;
    }
    this.runLookup(this.api.findParcelByRegion(query));
  }

  protected findParcel(): void {
    const id = this.model().parcelId.trim();
    if (id.length < 3 || id === this.lastLookedUp) return;
    this.runLookup(this.api.findParcel({ id }));
  }

  /** Karta znalezionej działki dotyczy poprzedniego numeru — chowamy ją przy edycji. */
  protected parcelEdited(): void {
    if (this.model().parcelId.trim() !== this.lastLookedUp) {
      this.lookupSeq++;
      this.lookup.set({ state: 'idle' });
    }
  }

  protected useCandidate(candidate: ParcelCandidate): void {
    this.model.update((m) => ({ ...m, parcelId: candidate.id }));
    this.lastLookedUp = '';
    this.runLookup(this.api.findParcel({ id: candidate.id }));
  }

  /** Kliknięcie w mapę: działka w tym punkcie (ULDK) — numer trafia do pola, granica na mapę. */
  protected pickOnMap(point: PickedPoint): void {
    this.runLookup(this.api.findParcel({ lat: point.lat, lon: point.lon }));
  }

  protected useMyLocation(): void {
    if (this.locating()) return;
    if (!('geolocation' in navigator)) {
      this.lookup.set({ state: 'error', message: 'Ta przeglądarka nie udostępnia lokalizacji. Wpisz numer działki.', candidates: [] });
      return;
    }
    this.locating.set(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        this.locating.set(false);
        this.runLookup(this.api.findParcel({ lat: coords.latitude, lon: coords.longitude }));
      },
      () => {
        this.locating.set(false);
        this.lookup.set({
          state: 'error',
          message: 'Nie udało się ustalić lokalizacji. Zezwól na nią w przeglądarce albo wpisz numer działki.',
          candidates: [],
        });
      },
      { enableHighAccuracy: true, timeout: 15000 },
    );
  }

  /** „Dalej”: sprawdza tylko pole bieżącego kroku. */
  protected next(): void {
    const field = this.stepField(this.step())();
    field.markAsTouched();
    if (field.invalid()) {
      field.focusBoundControl();
      return;
    }
    this.goTo((this.step() + 1) as WizardStep);
  }

  protected back(): void {
    this.goTo((this.step() - 1) as WizardStep);
  }

  /** Wskaźnik kroków: powrót do kroku już odwiedzonego. */
  protected goTo(step: WizardStep): void {
    this.step.set(step);
    afterNextRender(() => this.stepHeading()?.nativeElement.focus(), { injector: this.injector });
  }

  private stepField(step: WizardStep) {
    return step === 1 ? this.analysis.parcelId : step === 2 ? this.analysis.date : this.analysis.crop;
  }

  protected async onSubmit(event: Event): Promise<void> {
    event.preventDefault();
    // Enter w polu przed ostatnim krokiem działa jak „Dalej”, a nie wysłanie analizy.
    if (this.step() < 3) {
      this.next();
      return;
    }
    this.serverError.set(null);
    this.focusTarget = null;
    await submit(this.analysis, {
      action: async () => {
        this.showSummary.set(false);
        const abort = (this.abort = new AbortController());
        const { parcelId, date, crop } = this.model();
        try {
          const report = await this.api.analyze({ parcel_id: parcelId.trim(), date, crop }, this.mock, abort.signal);
          if (abort.signal.aborted) return undefined;
          // Raport idzie też w stanie nawigacji — ekran raportu nie musi go pobierać drugi raz.
          await this.router.navigate(['/raport', report.id], { state: { report } });
        } catch (err) {
          if (abort.signal.aborted) this.focusTarget = 'form';
          else this.handleError(err as ApiError);
        }
        return undefined;
      },
      onInvalid: () => {
        this.showSummary.set(true);
        // wróć do pierwszego kroku z błędem — podsumowanie stoi nad krokami
        this.step.set(this.steps.find((s) => this.stepField(s.n)().invalid())?.n ?? this.step());
        this.focusTarget = 'summary';
      },
    });
    if (this.destroyed) return;
    // Widok (formularz / ładowanie / wynik) zmienia się dopiero po zakończeniu submit() — fokus po renderze.
    afterNextRender(() => this.moveFocus(), { injector: this.injector });
  }

  protected cancelAnalysis(): void {
    this.abort?.abort();
  }

  /** Link w podsumowaniu błędów: przełącz na krok z tym polem i ustaw na nim fokus. */
  protected focusField(error: { fieldTree: () => { focusBoundControl(): void } }): void {
    const owner = this.steps.find((s) => (this.stepField(s.n)().errors() as unknown[]).includes(error));
    if (owner) this.step.set(owner.n);
    afterNextRender(() => error.fieldTree().focusBoundControl(), { injector: this.injector });
  }

  private runLookup(request: Promise<Parcel>): void {
    // Odpowiedź starszego wyszukiwania nie może nadpisać nowszego numeru.
    const seq = ++this.lookupSeq;
    this.lookup.set({ state: 'loading' });
    request.then(
      (parcel) => {
        if (seq !== this.lookupSeq) return;
        this.lastLookedUp = parcel.id;
        this.model.update((m) => ({ ...m, parcelId: parcel.id }));
        this.lookup.set({ state: 'found', parcel });
      },
      (err: ApiError) => {
        if (seq === this.lookupSeq) this.lookup.set({ state: 'error', message: err.message, candidates: err.candidates });
      },
    );
  }

  private handleError(err: ApiError): void {
    if (err.status === 404) {
      this.lookup.set({ state: 'error', message: err.message, candidates: err.candidates });
      this.step.set(1);
      this.focusTarget = 'parcel';
      return;
    }
    this.serverError.set(err.message);
    this.focusTarget = 'error';
  }

  private moveFocus(): void {
    const targets = { summary: this.summary, form: this.formHeading, error: this.errorAlert };
    if (this.focusTarget === 'parcel') this.analysis.parcelId().focusBoundControl();
    else if (this.focusTarget) targets[this.focusTarget]()?.nativeElement.focus();
  }
}
