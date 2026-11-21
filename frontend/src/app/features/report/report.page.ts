import { DecimalPipe, DOCUMENT, I18nPluralPipe, Location, NgOptimizedImage } from '@angular/common';
import { httpResource } from '@angular/common/http';
import { afterNextRender, Component, computed, DestroyRef, effect, ElementRef, inject, Injector, input, signal, viewChild } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';

import { Limitation, Recommendation, Report, ReportSummary } from '../../core/report.model';
import { HttpErrorResponse } from '@angular/common/http';

import { LEVEL_CLASS, levelFromIrrigation, levelFromRisk } from './levels';
import { LevelBadge } from './ui/level-badge';
import { RecommendationList } from './ui/recommendation-list';
import { ReportSources } from './ui/report-sources';
import { RiskCalendar } from './ui/risk-calendar';
import { KolbaChat } from './ui/kolba-chat';
import { WaterGauge } from './ui/water-gauge';

/** Sekcje ograniczeń pokazywane przy kroku 1 / kroku 5 (pozostałe są w sekcji „Źródła”). */
const ASSESSMENT_SECTIONS = ['ocena', 'model wody', 'ocena historyczna', 'tło suszowe', 'meteo', 'gleba'];

@Component({
  selector: 'app-report-page',
  imports: [RouterLink, NgOptimizedImage, DecimalPipe, I18nPluralPipe, LevelBadge, WaterGauge, RiskCalendar, RecommendationList, ReportSources, KolbaChat],
  templateUrl: './report.page.html',
})
export class ReportPage {
  /** Parametr trasy /raport/:id (withComponentInputBinding). */
  readonly id = input.required<string>();

  private readonly document = inject(DOCUMENT);
  private readonly injector = inject(Injector);
  private readonly title = inject(Title);
  /** Raport przekazany z formularza w stanie nawigacji — oszczędza ponowne pobranie zaraz po analizie. */
  private readonly passed = (inject(Location).getState() as { report?: Report } | null)?.report;

  private readonly fromState = computed(() => (this.passed?.id === this.id() ? this.passed : undefined));
  protected readonly fetched = httpResource<Report>(() =>
    this.fromState() ? undefined : `/api/report/${encodeURIComponent(this.id())}`,
  );
  protected readonly notFound = computed(() => (this.fetched.error() as HttpErrorResponse | undefined)?.status === 404);
  // value() rzuca, gdy zasób jest w stanie błędu — czytamy tylko przez hasValue().
  protected readonly report = computed(() => this.fromState() ?? (this.fetched.hasValue() ? this.fetched.value() : undefined));
  /** /summary tylko dla starszych raportów, które nie mają jeszcze Report.summary. */
  protected readonly summaryResource = httpResource<ReportSummary>(() => {
    const r = this.report();
    return r && !r.summary ? `/api/report/${encodeURIComponent(r.id)}/summary` : undefined;
  });
  /** Ocena ryzyka (headline, risk_level) liczona wyłącznie w backendzie — frontend jej nie szacuje. */
  protected readonly summary = computed(
    () => this.report()?.summary ?? (this.summaryResource.hasValue() ? this.summaryResource.value() : undefined),
  );

  protected readonly soilWater = computed(() => this.report()?.water?.soil_water ?? null);
  protected readonly level = computed(() => levelFromRisk(this.summary()?.risk_level));
  protected readonly hasAssessment = computed(() => !!this.report()?.water);
  protected readonly retention = computed(() => this.byCategory('retencja'));
  protected readonly agrotech = computed(() => this.byCategory('agrotechnika'));
  protected readonly causes = computed(() => [...(this.report()?.causes ?? [])].sort((a, b) => a.rank - b.rank));
  protected readonly maxContribution = computed(() => Math.max(1, ...this.causes().map((c) => c.contribution_mm ?? 0)));
  protected readonly waterConfidence = computed(() => this.report()?.confidence.find((c) => c.section === 'ocena wilgotności'));
  protected readonly assessmentNotes = computed(() => this.notes((l) => ASSESSMENT_SECTIONS.includes(l.section ?? '')));
  protected readonly irrigationNotes = computed(() => this.notes((l) => l.section === 'nawadnianie'));
  protected readonly irrigationLevel = computed(() => {
    const status = this.report()?.irrigation?.status;
    return status ? levelFromIrrigation(status) : 'unknown';
  });
  protected readonly levelClass = LEVEL_CLASS;
  protected readonly doses = { '=1': 'dawka', '=2': 'dawki', '=3': 'dawki', '=4': 'dawki', other: 'dawek' };
  protected readonly mapFailed = signal(false);

  private readonly heading = viewChild<ElementRef<HTMLElement>>('heading');
  private readonly kolbaDialog = viewChild<ElementRef<HTMLDialogElement>>('kolbaDialog');

  /** ≥ 64rem Kolba siedzi w kolumnie bocznej, niżej w oknie dialogowym (DESIGN.md §6.4). */
  protected readonly wide = signal(false);

  constructor() {
    const query = this.document.defaultView?.matchMedia?.('(width >= 64rem)');
    if (query) {
      this.wide.set(query.matches);
      const onChange = (e: MediaQueryListEvent) => this.wide.set(e.matches);
      query.addEventListener('change', onChange);
      inject(DestroyRef).onDestroy(() => query.removeEventListener('change', onChange));
    }

    effect(() => {
      const r = this.report();
      if (!r && !this.fetched.error()) return;
      this.title.setTitle(r ? `Raport — działka ${r.parcel.id} — Wodiva` : 'Raport niedostępny — Wodiva');
      afterNextRender(() => this.heading()?.nativeElement.focus(), { injector: this.injector });
    });
  }

  /** showModal(): fokus w środku, Esc zamyka, po zamknięciu przeglądarka oddaje fokus przyciskowi. */
  protected openKolba(): void {
    this.kolbaDialog()?.nativeElement.showModal();
  }

  protected print(): void {
    this.document.defaultView?.print();
  }

  private byCategory(category: Recommendation['category']): Recommendation[] {
    return this.report()?.recommendations.filter((r) => r.category === category) ?? [];
  }

  private notes(match: (l: Limitation) => boolean): Limitation[] {
    return this.report()?.limitations.filter((l) => l.severity !== 'info' && match(l)) ?? [];
  }
}
