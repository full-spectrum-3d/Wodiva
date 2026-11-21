import { DecimalPipe, I18nPluralPipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';

import { Report } from '../../../core/report.model';
import { LEVEL_CLASS, levelFromIrrigation } from '../levels';
import { LevelBadge } from '../ui/level-badge';

/** Zakładka 5: ocena nawadniania (bez oceny stanu wody — wyjaśnienie, nie zalecenia). */
@Component({
  selector: 'app-irrigation-tab',
  imports: [DecimalPipe, I18nPluralPipe, LevelBadge],
  templateUrl: './irrigation-tab.html',
})
export class IrrigationTab {
  readonly report = input.required<Report>();

  protected readonly notes = computed(() => this.report().limitations.filter((l) => l.severity !== 'info' && l.section === 'nawadnianie'));
  protected readonly level = computed(() => {
    const status = this.report().irrigation?.status;
    return status ? levelFromIrrigation(status) : 'unknown';
  });
  protected readonly levelClass = LEVEL_CLASS;
  protected readonly doses = { '=1': 'dawka', '=2': 'dawki', '=3': 'dawki', '=4': 'dawki', other: 'dawek' };
}
