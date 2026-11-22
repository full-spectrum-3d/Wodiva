import { DatePipe, DecimalPipe, DOCUMENT, Location } from '@angular/common';
import { HttpErrorResponse, httpResource } from '@angular/common/http';
import { afterNextRender, Component, computed, effect, ElementRef, inject, Injector, input, linkedSignal, viewChild } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { Router, RouterLink } from '@angular/router';

import { Report } from '../../core/report.model';
import { AgrotechTab } from './tabs/agrotech-tab';
import { AssessmentTab } from './tabs/assessment-tab';
import { CausesTab } from './tabs/causes-tab';
import { IrrigationTab } from './tabs/irrigation-tab';
import { panelId, REPORT_TABS, ReportTabId, ReportTabs, tabFromParam, tabId } from './tabs/report-tabs';
import { RetentionTab } from './tabs/retention-tab';
import { SourcesTab } from './tabs/sources-tab';
import { levelFromRisk } from './levels';
import { ParcelMap } from './map/parcel-map';
import { KolbaAvatar } from './ui/kolba-avatar';
import { KolbaChat } from './ui/kolba-chat';
import { LevelBadge } from './ui/level-badge';

/** Nazwa parametru zapytania z wybraną zakładką, np. ?zakladka=nawadnianie. */
const TAB_QUERY_PARAM = 'zakladka';

@Component({
  selector: 'app-report-page',
  imports: [
    RouterLink, DecimalPipe, DatePipe, KolbaAvatar, KolbaChat, LevelBadge, ReportTabs, ParcelMap,
    AssessmentTab, CausesTab, RetentionTab, AgrotechTab, IrrigationTab, SourcesTab],
  templateUrl: './report.page.html',
})
export class ReportPage {
  /** Parametr trasy /raport/:id (withComponentInputBinding). */
  readonly id = input.required<string>();
  /** Parametr zapytania ?zakladka= (withComponentInputBinding) — wybrana zakładka, przeżywa odświeżenie. */
  readonly zakladka = input<string>();

  private readonly document = inject(DOCUMENT);
  private readonly injector = inject(Injector);
  private readonly router = inject(Router);
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

  protected readonly tabs = REPORT_TABS;
  protected readonly level = computed(() => levelFromRisk(this.report()?.summary?.risk_level));
  protected readonly tabId = tabId;
  protected readonly panelId = panelId;
  /** Źródłem prawdy jest URL; linkedSignal pozwala przełączyć zakładkę od razu, bez czekania na nawigację. */
  protected readonly tab = linkedSignal<ReportTabId>(() => tabFromParam(this.zakladka()));

  private readonly heading = viewChild<ElementRef<HTMLElement>>('heading');
  private readonly kolbaDialog = viewChild<ElementRef<HTMLDialogElement>>('kolbaDialog');
  private readonly kolbaChat = viewChild(KolbaChat);

  constructor() {
    this.title.setTitle('Raport — Wodiva');
    effect(() => {
      const r = this.report();
      if (!r && !this.fetched.error()) return;
      this.title.setTitle(r ? `Raport — działka ${r.parcel.id} — Wodiva` : 'Raport niedostępny — Wodiva');
      afterNextRender(() => this.heading()?.nativeElement.focus(), { injector: this.injector });
    });
  }

  protected selectTab(id: ReportTabId): void {
    this.tab.set(id);
    // replaceUrl: przełączanie zakładek nie zaśmieca historii przeglądarki.
    void this.router.navigate([], { queryParams: { [TAB_QUERY_PARAM]: id }, queryParamsHandling: 'merge', replaceUrl: true });
  }

  /** showModal(): fokus w środku, Esc zamyka, po zamknięciu przeglądarka oddaje fokus wyzwalaczowi. */
  openKolba(): void {
    this.kolbaDialog()?.nativeElement.showModal();
    this.kolbaChat()?.prepare();
  }

  protected print(): void {
    this.document.defaultView?.print();
  }
}
