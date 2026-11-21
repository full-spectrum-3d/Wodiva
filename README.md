# Wodiva – asystent wody dla działki rolnej

Zespół: _(nazwa zespołu)_ · HackNation 2026 · zadanie KOWR „Zatrzymaj wodę, chroń plony”

Rolnik podaje identyfikator działki ewidencyjnej (albo klika na mapie), datę z ostatnich 10 lat i uprawę. Wodiva pobiera dane meteorologiczne, satelitarne, glebowe, hydrologiczne i przestrzenne, liczy stan wody na działce i jej historyczną podatność na suszę, a potem podaje rekomendacje w kolejności: ocena → przyczyny → retencja → agrotechnika → nawadnianie.

## 1. Uruchomienie

### Codespaces / lokalnie (Python 3.12)

```bash
cp .env.example .env
cd backend
pip install -e ".[dev,era5]"
python -c "import duckdb; duckdb.connect().execute('INSTALL httpfs')"
uvicorn app.core.main:app --reload --port 8000
```

Sprawdzenie: `http://localhost:8000/api/health`, dokumentacja API: `http://localhost:8000/docs`.

Raport testowy bez internetu (dane syntetyczne):

```bash
curl -X POST "http://localhost:8000/api/analyze?mock=true" -H "Content-Type: application/json" \
  -d '{"parcel_id":"141201_1.0001.6509","date":"2025-07-01","crop":"pszenica_ozima"}'
```

### Docker

```bash
cp .env.example .env
docker compose up --build
docker compose --profile era5 up -d era5-updater
```

### Kostka ERA5-Land (historia meteo)

Bez klucza CDS (gotowa kostka): `python -m scripts.download_era5_cube --url <link z sekcji 5>`.

Z własnym kluczem CDS (konto na cds.climate.copernicus.eu, akceptacja licencji ERA5-Land, `CDSAPI_KEY` w `.env`):

```bash
cd backend
python -m scripts.build_era5_cube --start 2015-01-01
python -m scripts.update_era5
```

Bez kostki aplikacja działa dalej: historię pobiera z archiwum Open-Meteo (wolniej, z limitem dziennym).

### Testy i kontrola źródeł

```bash
cd backend
pytest
ruff check .
python -m scripts.smoke_sources --parcel 141201_1.0001.6509 --lat 51.42 --lon 21.97
python -m scripts.validate --limit 5
```

## 2. Funkcjonalności

- Wyszukanie działki po identyfikatorze (z arkuszem i bez), po nazwie obrębu i numerze albo po punkcie na mapie; działki wieloczęściowe; zapas: eksport EGiB `0_dzialki.parquet`.
- Użytek gruntowy z EGiB (próbkowanie kilku punktów działki); działka nierolnicza → brak zaleceń nawadniania.
- Meteo dzienne od 2015 r.: ERA5-Land (kostka), ostatnie dni i prognoza 7 dni z Open-Meteo, kontrola ze stacją synoptyczną IMGW-PIB.
- ET0 liczone samodzielnie metodą FAO-56 Penman-Monteith.
- Klimatyczny bilans wodny (KBW) w okresach sześciodekadowych i progi suszy wg rozporządzenia MRiRW (Dz.U. 2019 poz. 739) dla uprawy i kategorii gleby.
- SPI 1 i 3 mies., anomalia ET0, dni upalne, okresy bez opadu, percentyl wobec tej samej daty z 10 lat, kalendarz ryzyka w dekadach.
- Gleba z SoilGrids (5 warstw 0–100 cm) → pojemność wodna (Saxton i Rawls 2006) → kategoria podatności IUNG.
- Dobowy bilans wody w glebie FAO-56 dla uprawy: zapas, zubożenie, dni stresu w sezonie, porównanie z 10 latami.
- Scenariusze „co jeśli”: mulcz/resztki, +1 p.p. materii organicznej, zatrzymanie spływu.
- Nawadnianie: zasadność, termin (z prognozą), dawka netto/brutto, objętość wody, informacja o pozwoleniu wodnoprawnym.
- Sentinel-2: NDVI, NDMI, NDWI, NDRE; pasma 20 m (B05, B8A, B11) wyostrzane do 10 m; piksele ważone udziałem powierzchni w działce; maska chmur SCL.
- Stan roślin wobec tej samej pory roku w 9 poprzednich latach (VCI); lata bez Sentinel-2 uzupełnia Landsat 5/7/8/9; brakujące lata dociągane w tle do pamięci podręcznej.
- Fenologia upraw: faza rozwoju, rozpoznanie zbioru i gołej gleby (niski NDVI po zbiorze ≠ susza), przesunięcie faz w sezonie dla modelu wody.
- Sentinel-1: anomalia VV i VH/VV wobec poprzednich lat (niezależna od chmur).
- Teren z NMT (zapas: Copernicus DEM): spadek dla modelu wody, zagłębienia bezodpływowe, linie spływu, TWI.
- Hydrologia z BDOT10k: rowy melioracyjne, cieki, wody, mokradła, zadrzewienia, budowle hydrotechniczne w promieniu 500 m.
- Tło suszowe: wskaźnik CDI z Europejskiego Obserwatorium Suszy.
- Przyczyny niedoboru z wkładem w mm (opad, upał, gleba, spływ, brak retencji w krajobrazie) i pewność każdej części raportu.
- Rekomendacje z reguł (`data/land/rules.yaml`) z rejestrem źródeł naukowych (`data/land/evidence.md`, E01–E22), uzasadnione liczbami działki i scenariuszami „co jeśli”, powiązane z ekoschematami; bez oceny nie ma rekomendacji.
- Raport: kolejność KOWR, mapa działki, PDF z kodem QR, zapis w SQLite i stały link (`/api/report/{id}`, `.pdf`, `/map.png`, `/summary`).
- Asystent „Kolba”: odpowiedzi wyłącznie z raportu działki i rejestru źródeł (Claude API), bez klucza tryb gotowych pytań.

## 3. Architektura

Python 3.12, FastAPI. Moduły `water/` (działka, meteo, gleba, model wody, nawadnianie) i `land/` (satelity, teren, hydrologia, przyczyny, rekomendacje) nie importują się nawzajem; wymiana przez `core/schemas.py` i `core/contracts.py`.

```
POST /api/analyze
  └─ water.parcel.resolve_by_id          ULDK → (zapas) EGiB parquet, EGiB użytki
  └─ gather(water.prepare, land.observe)  meteo + gleba ‖ satelity + teren + hydrologia
  └─ water.compute(prep, spadek, faza)    KBW, wskaźniki, bilans FAO-56, scenariusze, nawadnianie
  └─ land.interpret(...)                  przyczyny, rekomendacje, pewność
  └─ report.builder.build(...)            raport JSON (+ PDF)
```

Pamięć podręczna SQLite (`core/cache.py`) z czasem ważności per źródło; Open-Meteo buforowane na komórkę 0,1° i dzień, więc jedno zapytanie obsługuje wszystkich użytkowników z komórki. Klient HTTP z limitem czasu per źródło i ponowieniami; czas każdego źródła trafia do `timings_s` w raporcie.

## 4. Źródła i zakresy danych

| Kategoria | Źródło | Zakres | Licencja / warunki |
| :--- | :--- | :--- | :--- |
| Działka | ULDK GUGiK | cała Polska | dane publiczne GUGiK, bezpłatne |
| Działka (zapas) | EGiB `0_dzialki.parquet` (Geoportal opendata) | cała Polska | dane publiczne GUGiK |
| Użytek gruntowy | WMS KIEG (warstwy `uzytki`, `kontury`) | cała Polska | dane publiczne GUGiK / starostw |
| Meteo – historia | ERA5-Land, Copernicus C3S | 0,1°, dzienne od 2015 | Licence to use Copernicus Products |
| Meteo – ostatnie dni, prognoza | Open-Meteo | 0,1° (komórka), 31 dni wstecz + 7 dni | CC BY 4.0, API bezpłatne do użytku niekomercyjnego |
| Meteo – kontrola | IMGW-PIB, dane synoptyczne dobowe + bieżące | najbliższa stacja synop | dane publiczne IMGW-PIB, wymagane podanie źródła |
| Gleba | ISRIC SoilGrids 2.0 | 250 m, 0–100 cm | CC BY 4.0 |
| Progi suszy | Rozporządzenie MRiRW, Dz.U. 2019 poz. 739 (metodyka IUNG-PIB) | 4 kategorie gleb, 14 okresów | akt prawny |
| Uprawy | FAO-56 (Kc, korzenie, p), kalendarz dla Polski | 14 upraw | publikacja FAO |
| Satelita optyczny | Sentinel-2 L2A, katalog Earth Search (AWS) | 10 m, od 07.2015 | Copernicus data policy, bezpłatne |
| Satelita optyczny (lata wcześniejsze) | Landsat 5/7/8/9 C2 L2, Microsoft Planetary Computer | 30 m | USGS, domena publiczna |
| Radar | Sentinel-1 RTC, Microsoft Planetary Computer | 10 m, od 2017 | Copernicus data policy; RTC: CC BY 4.0 |
| Teren | NMT GRID1 (WCS Geoportal); zapas Copernicus DEM GLO-30 | 1 m / 30 m | dane PZGiK bezpłatne; Copernicus DEM z podaniem źródła |
| Hydrologia, pokrycie | BDOT10k, WMS kompozycja (Geoportal) | promień 500 m | dane PZGiK bezpłatne |
| Tło suszowe | Copernicus EDO, CDI (WMS) | ok. 5 km, co 10 dni od 2012 | Copernicus EMS, z podaniem źródła |

## 5. Dane na żywo i pobrane wcześniej

| Dane | Tryb | Data pobrania |
| :--- | :--- | :--- |
| ULDK, EGiB, Open-Meteo, IMGW, SoilGrids | na żądanie (z pamięcią podręczną) | w chwili analizy – data w sekcji źródeł raportu |
| Kostka ERA5-Land | pobrana wcześniej, aktualizacja codzienna | _(uzupełnić po zbudowaniu: zakres, data)_ ; link do pobrania: _(uzupełnić)_ |
| Progi KBW (`data/water/kbw_thresholds.csv`) | przepisane z aktu prawnego | 21.11.2026 |
| Parametry upraw (`data/water/crops.csv`) | przygotowane wcześniej | 21.11.2026 |
| Współrzędne stacji IMGW (`data/water/imgw_synop_stations.csv`) | przygotowane wcześniej, przybliżone | 21.11.2026 |
| Sentinel-2/1, Landsat, NMT, BDOT10k, EDO | na żądanie (pamięć podręczna `var/land_cache.sqlite`) | w chwili analizy – data w sekcji źródeł raportu |
| Fenologia, reguły, rejestr źródeł (`data/land/`) | przygotowane wcześniej | 21.11.2026 |

Wynik i rekomendacje zawsze liczy aplikacja na podstawie tych danych. Dla daty historycznej używane są wyłącznie dane do tej daty (bez prognozy i bez późniejszych obserwacji).

## 6. Biblioteki, usługi i AI

| Komponent | Licencja |
| :--- | :--- |
| FastAPI, Pydantic, pydantic-settings | MIT |
| Uvicorn, httpx | BSD-3-Clause |
| NumPy, pandas, SciPy, Dask | BSD-3-Clause |
| xarray | Apache-2.0 |
| zarr, netCDF4 | MIT |
| Shapely, rasterio | BSD-3-Clause |
| pyproj, DuckDB | MIT |
| cdsapi | Apache-2.0 |
| pytest, ruff | MIT |
| respx | BSD-3-Clause |
| Matplotlib | Matplotlib License (PSF) |
| ReportLab (open source) | BSD |
| PyYAML | MIT |
| anthropic (SDK) | MIT |

Żadna biblioteka nie jest na licencji GPL. Narzędzia AI: asystent „Kolba” używa Claude (Anthropic, `WODIVA_ASSISTANT_MODEL`, domyślnie `claude-opus-5-5`) przez płatne API; dostaje tylko raport działki i rejestr źródeł, nie liczy wyników; bez `ANTHROPIC_API_KEY` działa tryb gotowych pytań bez AI. Asystent AI użyty przy pisaniu kodu: _(uzupełnić)_. Liczby w raporcie pochodzą wyłącznie z silnika obliczeniowego, nigdy z modelu językowego.

## 7. Licencje i płatne usługi

- Open-Meteo: bezpłatne tylko do użytku niekomercyjnego. Przy wdrożeniu w KOWR: plan płatny Open-Meteo (`OPENMETEO_API_KEY`) albo samodzielnie: kostka ERA5-Land + IMGW (bez prognozy) lub własna instancja Open-Meteo (kod AGPL, uruchamiany jako osobna usługa).
- ERA5-Land i SoilGrids: bezpłatne, wymagają podania źródła.
- CDS API: bezpłatne konto i klucz, kolejka zleceń.

## 8. Znane ograniczenia

- ERA5-Land ma opóźnienie ok. 5 dni i rozdzielczość ok. 9 km – opad konwekcyjny lokalnie może się różnić; raport pokazuje porównanie ze stacją IMGW.
- Średni wiatr dobowy z 4 terminów (00, 06, 12, 18 UTC).
- KBW liczony jako opad − ET0 Penman-Monteith; IUNG używa własnej formuły ewapotranspiracji, więc wartości mogą się nieco różnić.
- Mapa kategorii gleb IUNG nie ma publicznego API – kategoria wyznaczana z uziarnienia SoilGrids (250 m), można ją podać ręcznie (`soil_category`).
- Model wody w glebie: jedna warstwa (FAO-56, pojedynczy Kc), bez kapilarnego podsiąku z wód gruntowych, bez śniegu i zamarzania; spływ uproszczony (spadek + kategoria gleby).
- SPI z ok. 10 lat ma ograniczoną dokładność w skrajnych wartościach.
- Współrzędne stacji IMGW są przybliżone (do kilku km).
- Sentinel-2 ma piksel 10 m: działki mniejsze niż ok. 0,3 ha mają niską pewność oceny satelitarnej. Porównanie z poprzednimi latami nie uwzględnia zmiany uprawy na działce; lata z Landsat (30 m) dają porównanie przybliżone.
- Limit części satelitarno-terenowej to 22 s: przy wolnym łączu część lat odniesienia nie zdąży – raport to podaje, a brakujące lata dociągają się w tle na kolejną analizę.
- Gdy WCS NMT nie odpowiada, używany jest Copernicus DEM 30 m (model powierzchni z roślinnością i zabudową): miejsca retencji są orientacyjne.
- BDOT10k odczytywany z WMS jako raster (siatka 2,5 m): odległości przybliżone do kilku metrów.
- Brak danych o wodach podziemnych: usługi PIG-PIB i Hydroportalu ISOK (MPHP) nie były publicznie dostępne; cieki i rowy pochodzą z BDOT10k.
- Radar opisuje wierzchnią warstwę gleby i roślinność; świeży opad zaburza sygnał.

## 9. Weryfikacja wyników

- Testy jednostkowe (`pytest`): ET0 na przykładach z FAO-56 (przykład 18 – Bruksela, 3,9 mm/d), pedotransfer na tabeli Saxton i Rawls, bilans masy modelu wody, granice zapasu, „więcej opadu = mniej stresu”, okresy i progi KBW z rozporządzenia, brak danych po dacie analizy.
- `scripts/validate.py`: 20 działek z 16 województw × daty (2015, 2017, 2018, 2019, dziś); czas analizy, opad ERA5 vs IMGW, susza KBW vs IUNG Monitoring Suszy (porównanie ręczne) → `docs/validation.md`.
- `scripts/smoke_sources.py`: sprawdzenie dostępności każdego źródła.
- Testy części B (`tests/land/`): wyostrzanie pasm, wagi pikseli, VCI, fenologia i przesunięcie faz, maska chmur Landsat, analiza terenu na syntetycznym NMT, reguły, kolejność etapów, raport PDF, API raportu i asystenta, pełny przebieg `/api/analyze` z częścią B.

## Skalowalność

- Limity źródeł: pamięć podręczna na źródło (gleba 1 rok, działka 30 dni, meteo bieżące 3 h), Open-Meteo na komórkę siatki zamiast na użytkownika, limit zapytań na IP.
- Historia meteo lokalnie (kostka Zarr ~0,3 GB): odczyt serii działki w milisekundach, bez zależności od zewnętrznego API.
- Przy dużym ruchu: kilka instancji backendu za load balancerem, wspólny cache (Redis zamiast SQLite), kostka ERA5 w obiektowym magazynie (S3).
- Koszty: _(uzupełnić)_
