import { DecimalPipe } from '@angular/common';
import { httpResource } from '@angular/common/http';
import { Component, computed, input } from '@angular/core';

import { Limitation, Report, ReportSummary } from '../../../core/report.model';
import { LEVEL_CLASS, levelFromRisk } from '../levels';
import { LevelBadge } from '../ui/level-badge';
import { RiskCalendar } from '../ui/risk-calendar';
import { WaterGauge } from '../ui/water-gauge';

/** Sekcje ograniczeń pokazywane przy ocenie (pozostałe są w zakładce „Źródła”). */
const ASSESSMENT_SECTIONS = ['ocena', 'model wody', 'ocena historyczna', 'tło suszowe', 'meteo', 'gleba'];

/** Zakładka 1: ocena stanu wody, wodowskaz i kalendarz ryzyka (mapa jest obok zakładek). */
@Component({
  selector: 'app-assessment-tab',
  imports: [DecimalPipe, LevelBadge, WaterGauge, RiskCalendar],
  templateUrl: './assessment-tab.html',
})
export class AssessmentTab {
  readonly report = input.required<Report>();

  /** /summary tylko dla starszych raportów, które nie mają jeszcze Report.summary. */
  protected readonly summaryResource = httpResource<ReportSummary>(() => {
    const r = this.report();
    return r.summary ? undefined : `/api/report/${encodeURIComponent(r.id)}/summary`;
  });
  /** Ocena ryzyka (headline, risk_level) liczona wyłącznie w backendzie — frontend jej nie szacuje. */
  protected readonly summary = computed(
    () => this.report().summary ?? (this.summaryResource.hasValue() ? this.summaryResource.value() : undefined),
  );
  protected readonly level = computed(() => levelFromRisk(this.summary()?.risk_level));
  protected readonly soilWater = computed(() => this.report().water?.soil_water ?? null);
  protected readonly waterConfidence = computed(() => this.report().confidence.find((c) => c.section === 'ocena wilgotności'));
  protected readonly notes = computed(() =>
    this.report().limitations.filter((l: Limitation) => l.severity !== 'info' && ASSESSMENT_SECTIONS.includes(l.section ?? '')),
  );
  protected readonly levelClass = LEVEL_CLASS;
}
