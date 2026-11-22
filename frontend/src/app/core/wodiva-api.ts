import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import { firstValueFrom, fromEvent, takeUntil } from 'rxjs';

import { Report } from './report.model';
import { AddressQuery, AnalyzeRequest, ApiError, AssistantAnswer, Parcel, ParcelCandidate, RegionQuery } from './wodiva-api.model';

@Service()
export class WodivaApi {
  private readonly http = inject(HttpClient);

  findParcel(query: { id: string } | { lat: number; lon: number }): Promise<Parcel> {
    return this.getParcel('/api/parcel', query);
  }

  findParcelByAddress(query: AddressQuery): Promise<Parcel> {
    return this.getParcel('/api/parcel/address', { ...query });
  }

  findParcelByRegion(query: RegionQuery): Promise<Parcel> {
    return this.getParcel('/api/parcel/region', { ...query });
  }

  /** `abort` przerywa żądanie; obietnica jest wtedy odrzucana — wołający sprawdza `signal.aborted`. */
  analyze(body: AnalyzeRequest, mock: boolean, abort: AbortSignal): Promise<Report> {
    const params = mock ? new HttpParams().set('mock', 'true') : undefined;
    const request = this.http.post<Report>('/api/analyze', body, { params }).pipe(takeUntil(fromEvent(abort, 'abort')));
    return firstValueFrom(request).catch((err: unknown) => Promise.reject(toApiError(err)));
  }

  askKolba(reportId: string, question: string): Promise<AssistantAnswer> {
    return firstValueFrom(this.http.post<AssistantAnswer>('/api/assistant', { report_id: reportId, question })).catch(
      (err: unknown) => Promise.reject(toApiError(err)),
    );
  }

  prepareKolba(reportId: string): Promise<boolean> {
    return firstValueFrom(this.http.post<{ ready: boolean }>('/api/assistant/prepare', { report_id: reportId })).then(
      (res) => res.ready,
      () => false,
    );
  }

  private getParcel(url: string, query: Record<string, string | number>): Promise<Parcel> {
    const params = new HttpParams({ fromObject: query });
    return firstValueFrom(this.http.get<{ parcel: Parcel; address?: string }>(url, { params }))
      .then((res) => (res.address ? { ...res.parcel, address_label: res.address } : res.parcel))
      .catch((err: unknown) => Promise.reject(toApiError(err)));
  }
}

const NETWORK_MESSAGE = 'Nie udało się połączyć z serwerem analiz. Sprawdź internet i spróbuj ponownie.';

/** FastAPI zwraca `detail` jako tekst, `{message, candidates}` (404 działki) albo listę błędów Pydantic. */
export function toApiError(err: unknown): ApiError {
  if (!(err instanceof HttpErrorResponse) || err.status === 0 || err.status >= 500) {
    const detail = err instanceof HttpErrorResponse && typeof err.error?.detail === 'string' ? err.error.detail : null;
    return { status: err instanceof HttpErrorResponse ? err.status : 0, message: detail ?? NETWORK_MESSAGE, candidates: [] };
  }
  const detail: unknown = err.error?.detail;
  if (typeof detail === 'string') {
    return { status: err.status, message: detail, candidates: [] };
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const d = detail as { message: string; candidates?: ParcelCandidate[] };
    return { status: err.status, message: d.message, candidates: d.candidates ?? [] };
  }
  return { status: err.status, message: 'Serwer odrzucił dane formularza. Sprawdź pola i spróbuj ponownie.', candidates: [] };
}
