# Kontrakt A ↔ B

Modele danych: `backend/app/core/schemas.py`. Interfejsy: `backend/app/core/contracts.py`.
`core/` zmienia osoba A po uzgodnieniu z B.

## Co B udostępnia

`backend/app/land/service.py`:

```python
async def observe(parcel: Parcel, analysis_date: date, crop: str) -> LandObservation
def interpret(parcel: Parcel, water: WaterState, soil: SoilInfo,
              irrigation: IrrigationAdvice, land: LandObservation) -> LandInterpretation
```

- `observe` – Sentinel-2/1, teren, hydrologia, EDO. Limit czasu po stronie `analyze.py`: 22 s.
- `LandObservation.terrain.slope_mean_pct` → spływ w modelu wody A.
- `LandObservation.satellite.phase_offset_days` → przesunięcie faz uprawy w bieżącym sezonie (dni, + = później).
- `interpret` – przyczyny, rekomendacje, pewność; wołane dopiero po ocenie (kolejność KOWR).

`backend/app/report/builder.py`:

```python
def build(data: ReportInput) -> Report
def persist(report: Report) -> Report   # summary + mapa + zapis w report/store.py
```

`build` kończy się wywołaniem `persist`. `analyze.py` woła `persist` także dla atrapy, więc raport `?mock=true` ma te same endpointy co zwykły (`/report/{id}`, `/summary`, PDF, mapa, asystent).

Opcjonalnie routery: `app/report/api.py` i `app/assistant/api.py` z obiektem `router` (APIRouter) – `core/main.py` dołącza je automatycznie pod `/api`.

Dopóki tych modułów nie ma, `analyze.py` działa bez nich (limitacja `land_missing`, domyślny builder).

## Co A daje B

- `Parcel` – geometria (EPSG:2180 WKT + GeoJSON 4326), pole, flagi `size_class`, `is_agricultural`, `land_use`.
- `WaterState.climate` – KBW, próg, SPI, ET0, dni upalne, okresy bez opadu, kalendarz ryzyka.
- `WaterState.soil_water` – zapas, zubożenie, Ks, dni stresu, spływ w sezonie (mm), percentyl z 10 lat.
- `WaterState.scenarios` – wynik „co jeśli” (mulcz, próchnica, spływ) do uzasadnień agrotechnicznych.
- `SoilInfo` – warstwy, kategoria IUNG, pojemność wodna 0–100 cm.
- `IrrigationAdvice` – status, termin, dawka, objętość, uwaga prawna.
- `DataSource` / `Limitation` – każdy moduł zwraca swoje; raport składa listy.

## Raport

- `Report.summary: RiskSummary | None` – ocena ryzyka (`status`, `risk_level`, `headline`, `findings`) liczona przez B w `persist`. `GET /report/{id}/summary` zwraca to samo plus `report_id` (starsze raporty bez `summary` są liczone na żądanie).
- `Report.id` – 12 znaków hex, także dla atrapy; atrapę rozpoznaje się po `Report.mock`.

## Data analizy

„Dziś” w `validate_analysis_date` to dzień w strefie Europe/Warsaw (`today_in_poland()`), niezależnie od strefy serwera.

## Rejestr źródeł

- `GET /api/evidence` – cały `data/land/evidence.md` (markdown).
- `GET /api/evidence/{id}` – jedna pozycja jako JSON `{id, source, purpose}`; 404 dla nieznanego id.

## Atrapa

`POST /api/analyze?mock=true` – pełny `Report` na danych syntetycznych (prawdziwy silnik wody, przykładowe sekcje B), zapisany jak zwykły raport.
