import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { EvidenceDialogHost } from './core/evidence/evidence-dialog-host';

@Component({
  imports: [RouterOutlet, EvidenceDialogHost],
  selector: 'app-root',
  templateUrl: './app.html',
})
export class App {}
