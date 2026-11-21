import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'Sprawdź wodę na działce — Wodiva',
    loadComponent: () => import('./features/analysis/analysis-form.page').then((m) => m.AnalysisFormPage),
  },
  {
    path: 'raport/:id',
    title: 'Raport — Wodiva',
    loadComponent: () => import('./features/report/report.page').then((m) => m.ReportPage),
  },
  { path: '**', redirectTo: '' },
];
