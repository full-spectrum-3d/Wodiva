# Wodiva – asystent wody dla działki rolnej

HackNation 2026 · zadanie KOWR „Zatrzymaj wodę, chroń plony” · zespół: `[NAZWA ZESPOŁU]`

Rolnik podaje numer działki ewidencyjnej (albo wskazuje ją na mapie), uprawę i datę. Wodiva pobiera dla tej działki dane meteorologiczne, satelitarne, glebowe, hydrologiczne i przestrzenne z ostatnich 10 lat i liczy:

- ile wody jest teraz w glebie,
- jak często działka cierpi na niedobór wody,
- dlaczego tak jest.

Na tej podstawie podaje rekomendacje w kolejności wymaganej przez KOWR: retencja → agrotechnika → nawadnianie. Wynik to raport z mapą działki, do pobrania jako PDF.

| Materiał zgłoszenia | Gdzie |
| :--- | :--- |
| Działająca wersja | `[LINK DO APLIKACJI]` |
| Repozytorium (prywatne) | `[LINK DO REPOZYTORIUM]` |
| Prezentacja PDF (do 10 slajdów) | `[ŚCIEŻKA / LINK]` |
| Film z działania (do 3 min) | `[LINK]` |
| Raporty wygenerowane przez prototyp | `[ŚCIEŻKA, np. docs/raporty/]` |

## Problem, rozwiązanie, korzyści

**Problem.** Dane o wodzie istnieją, ale są rozproszone w kilkunastu serwisach (IMGW, Copernicus, GUGiK, PIG-PIB, IUNG, Wody Polskie), każdy w innym formacie. Rolnik bez znajomości GIS nie złoży z nich odpowiedzi na pytanie: czy moja działka jest sucha, dlaczego i co mam zrobić.

**Rozwiązanie.** Jedno zapytanie: działka + uprawa + data. Aplikacja sama:

- znajduje działkę w ULDK;
- pobiera i łączy dane z pięciu kategorii wymaganych przez KOWR;
- liczy bilans wody w glebie dla wybranej uprawy (FAO-56);
- porównuje stan z tą samą datą w poprzednich 10 latach;
- wskazuje przyczyny niedoboru i miejsca na działce, gdzie można zatrzymać wodę.

**Wykorzystanie danych.** Każda liczba w raporcie pochodzi z pobranych danych i obliczeń w kodzie. Model językowy nie liczy wyników. Każde źródło jest w raporcie wymienione z datą pobrania, licencją i statusem (ok / częściowo / brak).

**Korzyści dla rolnika:**

- konkretne działania z uzasadnieniem liczbowym dla tej działki, np. „zastawka na rowie 60 m od działki”, „międzyplon: o 7 dni stresu wodnego mniej w roku 2019”;
- kalendarz ryzyka suszy dla działki;
- ocena, czy i kiedy nawadniać, z dawką i informacją o pozwoleniu wodnoprawnym;
- powiązanie zaleceń z ekoschematami;
- uczciwa informacja, czego dane nie mówią.

## Zgodność z wymaganiami zadania

| Wymaganie (opis zadania KOWR) | Realizacja w Wodiva |
| :--- | :--- |
| 3.2 Aplikacja webowa w przeglądarce, bez instalowania oprogramowania | backend FastAPI + interfejs w przeglądarce `[uzupełnić: link]`; rolnik niczego nie instaluje |
| 3.3.2 Działka po identyfikatorze lub z mapy, dowolna w Polsce | `GET /api/parcel?id=` lub `?lat=&lon=` (ULDK GUGiK; zapas: eksport EGiB); działki wieloczęściowe, małe i nierolnicze obsłużone z ostrzeżeniem |
| 3.3.3 Wybór uprawy | 14 upraw (`GET /api/crops`), m.in. pszenica ozima, kukurydza, rzepak, ziemniak, burak, użytki zielone |
| 3.2.1 / 3.3.4 Ocena stanu wilgotności z danych z ostatnich 10 lat, bieżąca i historyczna | bilans wody w glebie i klimatyczny bilans wodny za 10 lat, percentyl wobec tej samej daty, kalendarz ryzyka, stan roślin wobec 9 poprzednich lat |
| 3.2.1a Interpretacja satelitarna wg uprawy | fazy rozwoju upraw: niski NDVI po zbiorze lub przed siewem nie jest traktowany jako susza |
| 3.2.2 Rekomendacje retencyjne i agrotechniczne z rzeźby terenu i hydrologii | zagłębienia i linie spływu z NMT, rowy, cieki, zbiorniki, mokradła (BDOT10k), wody podziemne (PIG-PIB) |
| 3.2.3 Nawadnianie (opcjonalnie) | zasadność, termin z prognozą 7 dni, dawka netto/brutto, objętość wody |
| Kolejność etapów, brak rekomendacji bez oceny | wymuszona w kodzie: bez bilansu wodnego raport nie zawiera przyczyn ani rekomendacji |
| 3.3.4 Wynik liczony z pobranych danych, nie gotowe rekomendacje | wszystkie wartości liczone przy każdej analizie; reguły rekomendacji wypełniane liczbami działki |
| 3.3.5 Raport: stan i przyczyny, rekomendacje z uzasadnieniem, data i źródła, ograniczenia, niepewność, brak danych wprost | sekcje raportu: ocena, przyczyny (mm), rekomendacje (z identyfikatorami źródeł), pewność każdej części, braki danych, ograniczenia, źródła z datami |
| 3.3.6 Zapis w systemie, PDF, druk | raport zapisywany ze stałym linkiem `/api/report/{id}`, PDF `/api/report/{id}.pdf` z mapą i kodem QR |
| 3.3 Pięć kategorii danych | meteorologiczne, satelitarne, glebowe, hydrologiczne, przestrzenne – tabela w sekcji 4 |
| 6 Dowolna działka i data z ostatnich 10 lat; dla daty historycznej tylko dane do tej daty | każde źródło obcina dane do daty analizy; testy `test_date_rule.py` i testy PIG-PIB |
| 7.5 Wynik do 30 s | walidacja A: mediana 8,9 s, maks. 29,2 s (22 działki); część satelitarno-terenowa ma limit 22 s |
| 4.2 README: punkty 1–9 | sekcje 1–9 poniżej |
| 5.4 Płatne usługi wskazane, z kosztami i alternatywą | sekcja 7 |
| 5.5 Skalowalność | sekcja 10 |
| 5.6 Bezpieczeństwo, brak danych osobowych | sekcja 11 |

## 1. Uruchomienie

Wymagania: Python 3.12. Na Windows polecenia są takie same, tylko aktywacja środowiska to `.venv\Scripts\Activate.ps1`.

```bash
cp .env.example .env
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,era5]"
python -c "import duckdb; duckdb.connect().execute('INSTALL httpfs')"
uvicorn app.core.main:app --port 8000
```

- Stan aplikacji i kostki ERA5: `http://localhost:8000/api/health`.
- Dokumentacja API z przyciskami „Try it out”: `http://localhost:8000/docs`.

Analiza działki:

```bash
curl -X POST http://localhost:8000/api/analyze -H "Content-Type: application/json" \
  -d '{"parcel_id":"040904_5.0023.248","date":"2025-07-15","crop":"kukurydza_ziarno"}'
```

Z odpowiedzi weź `id` i otwórz:

- `http://localhost:8000/api/report/{id}.pdf` – raport PDF,
- `http://localhost:8000/api/report/{id}/map.png` – mapa działki.

Raport testowy na danych syntetycznych, bez internetu: `POST /api/analyze?mock=true` z tym samym body.

**Docker** (backend + codzienna aktualizacja kostki ERA5):

```bash
cp .env.example .env
docker compose up --build -d
docker compose --profile era5 up -d era5-updater
```

**Kostka ERA5-Land** (historia meteo, patrz sekcja 5):

```bash
cd backend
python -m scripts.download_era5_cube --url "[LINK DO GOTOWEJ KOSTKI]"
python -m scripts.build_era5_cube --start 2015-01-01
python -m scripts.update_era5
```

- `download_era5_cube` pobiera gotową kostkę i nie wymaga klucza.
- `build_era5_cube` buduje kostkę od zera i wymaga `CDSAPI_KEY` w `.env`.
- `update_era5` dopisuje nowe dni do istniejącej kostki.

**Testy:**

```bash
cd backend
pytest
ruff check .
python -m scripts.smoke_sources --parcel 141201_1.0001.6509 --lat 51.42 --lon 21.97
python -m scripts.validate --limit 5
```

- `smoke_sources` sprawdza dostępność każdego źródła.
- `validate` uruchamia analizę na działkach z całej Polski.

## 2. Funkcjonalności

**Działka.**

- Wyszukiwanie po identyfikatorze (z arkuszem i bez), po nazwie obrębu i numerze albo po punkcie na mapie (ULDK).
- Gdy ULDK nie odpowiada, zapasem jest eksport EGiB `0_dzialki.parquet`.
- Użytek gruntowy z EGiB. Działka nierolnicza nie dostaje zaleceń nawadniania.

**1. Ocena stanu wilgotności.**

- Meteo dzienne od 2015 r. (ERA5-Land), ostatnie dni i prognoza 7 dni (Open-Meteo), kontrola z najbliższą stacją synoptyczną IMGW-PIB.
- Parowanie wzorcowe ET0 liczone metodą FAO-56 Penman-Monteith.
- Klimatyczny bilans wodny w okresach sześciodekadowych z progami suszy z rozporządzenia MRiRW (Dz.U. 2019 poz. 739), jak w systemie IUNG-PIB.
- Wskaźnik opadu SPI (1 i 3 mies.), anomalia ET0, dni upalne, okresy bez opadu.
- Gleba z SoilGrids (5 warstw do 100 cm) → pojemność wodna (Saxton i Rawls 2006) → kategoria podatności na suszę IUNG.
- Dobowy bilans wody w glebie FAO-56 dla wybranej uprawy: zapas, zubożenie, dni stresu, percentyl wobec tej samej daty w 10 latach, kalendarz ryzyka w dekadach.
- Sentinel-2:
  - wskaźniki NDVI, NDMI, NDWI, NDRE;
  - pasma 20 m wyostrzane do 10 m, piksele ważone udziałem powierzchni w działce, maska chmur;
  - stan roślin wobec tej samej pory roku w 9 poprzednich latach (VCI); lata bez Sentinel-2 uzupełnia Landsat.
- Faza rozwoju uprawy: niski NDVI po zbiorze nie jest odczytywany jako susza; przesunięcie faz w sezonie trafia do modelu wody.
- Sentinel-1 (radar, niezależny od chmur): anomalia sygnału wobec poprzednich lat.
- Wskaźnik suszy CDI z Europejskiego Obserwatorium Suszy jako tło regionalne.

**2. Przyczyny niedoboru wody.** Każda przyczyna ma wkład w milimetrach i opis z liczbami działki:

- niedobór opadów;
- upał i wysokie parowanie;
- mała pojemność wodna gleby;
- odpływ powierzchniowy;
- brak retencji w otoczeniu.

**3. Rekomendacje retencyjne.** Z modelu terenu (NMT, siatka 2–6 m) i hydrologii:

- **Zagłębienia bezodpływowe**, z powierzchnią i objętością: miejsca na oczko lub zastoisko.
- **Linie spływu**: pasy buforowe, uprawa w poprzek stoku.
- **Rowy melioracyjne**: zastawki, z informacją o uzgodnieniach według Prawa wodnego.
- **Cieki z identyfikatorem MPHP**: strefy buforowe.
- **Mokradła i zadrzewienia.**
- **Słaby stan ilościowy wód podziemnych**: priorytet retencji przed poborem.

Miejsca są zaznaczone na mapie działki.

**4. Rekomendacje agrotechniczne.**

- Zalecenia: międzyplony i okrywa gleby, zwiększanie próchnicy, uprawa uproszczona i mulcz, uprawa w poprzek stoku, monitoring w okresie ryzyka, dobór odmian.
- Każde zalecenie jest powiązane z przyczyną.
- Tam, gdzie się da, zalecenie ma wynik symulacji „co jeśli” dla tej działki (mulcz, +1 p.p. materii organicznej, zatrzymanie spływu).
- Zalecenia mają też odwołania do ekoschematów WPR i źródeł naukowych (`backend/data/land/evidence.md`, E01–E23).

**5. Nawadnianie.**

- Zasadność, termin (z prognozą opadu na 7 dni), dawka netto i brutto, objętość wody dla działki.
- Informacja o zgłoszeniu lub pozwoleniu wodnoprawnym.

**Raport i asystent.**

- Raport w kolejności KOWR, zapisany ze stałym linkiem, z PDF, mapą i podsumowaniem `/api/report/{id}/summary`.
- Asystent „Kolba” odpowiada na pytania rolnika wyłącznie na podstawie raportu jego działki i rejestru źródeł. Bez klucza API działa w trybie gotowych pytań.

## 3. Architektura

Python 3.12, FastAPI. Backend ma trzy części:

- `water/` – działka, meteo, gleba, model wody, nawadnianie;
- `land/` – satelity, teren, hydrologia, przyczyny, rekomendacje;
- `report/` z `assistant/` – raport i asystent.

`water/` i `land/` nie importują się nawzajem. Wymieniają dane przez modele w `core/schemas.py` i interfejsy w `core/contracts.py`.

```
POST /api/analyze
  ├─ water.parcel.resolve_by_id            ULDK → zapas EGiB parquet; użytki EGiB
  ├─ równolegle:
  │    water.prepare                       meteo (ERA5 + Open-Meteo + IMGW), gleba (SoilGrids, IUNG)
  │    land.observe          (limit 22 s)  Sentinel-2, Landsat, Sentinel-1, NMT, BDOT10k, PIG-PIB, EDO
  ├─ water.compute(spadek, faza uprawy)    KBW, wskaźniki, bilans FAO-56, scenariusze, nawadnianie
  ├─ land.interpret                        ocena, przyczyny, rekomendacje, pewność
  └─ report.builder.build                  raport JSON → zapis (SQLite) → PDF, mapa
```

- **Pamięć podręczna:** SQLite z czasem ważności osobnym dla każdego źródła (`var/cache.sqlite`, `var/land_cache.sqlite`), raporty w `var/reports.sqlite`.
- **Klient HTTP:** ma limit czasu dla każdego źródła i ponawia nieudane zapytania.
- **Czasy:** czas każdego źródła trafia do `timings_s` w raporcie.

## 4. Źródła i zakresy danych

| Kategoria KOWR | Dane | Źródło | Zakres | Licencja / warunki |
| :--- | :--- | :--- | :--- | :--- |
| Przestrzenne | Granica i identyfikator działki | ULDK GUGiK; zapas: EGiB `0_dzialki.parquet` (Geoportal opendata) | cała Polska | dane PZGiK, bezpłatne |
| Przestrzenne | Użytek gruntowy | WMS KIEG (`uzytki`, `kontury`) | cała Polska | dane PZGiK / starostw |
| Przestrzenne | Rzeźba terenu | NMT GUGiK – usługa wysokości `services.gugik.gov.pl/nmt` (GetHByPointList); zapas: Copernicus DEM GLO-30 | siatka 2–6 m (do 30 000 punktów); zapas 30 m | dane PZGiK; Copernicus DEM z podaniem źródła |
| Przestrzenne | Pokrycie terenu, zadrzewienia | BDOT10k, WMS „kompozycja BDOT10k” (Geoportal) | promień 500 m | dane PZGiK |
| Meteorologiczne | Historia dobowa: opad, temperatura, punkt rosy, wiatr, promieniowanie, ciśnienie | ERA5-Land, Copernicus C3S (kostka lokalna) | 0,1°, od 01.01.2015 | Licence to use Copernicus Products |
| Meteorologiczne | Ostatnie dni (których nie ma jeszcze w ERA5) i prognoza 7 dni | Open-Meteo | komórka 0,1° | CC BY 4.0; bezpłatnie do użytku niekomercyjnego |
| Meteorologiczne | Kontrola z pomiarem | IMGW-PIB, dane synoptyczne dobowe i bieżące | najbliższa stacja synop | dane publiczne IMGW-PIB, z podaniem źródła |
| Satelitarne | Stan roślin: NDVI, NDMI, NDWI, NDRE | Sentinel-2 L2A, katalog Earth Search (AWS) | 10 m, od 07.2015 | Copernicus data policy |
| Satelitarne | Lata odniesienia bez Sentinel-2 | Landsat 5/7/8/9 Collection 2 L2, Microsoft Planetary Computer | 30 m | USGS, domena publiczna |
| Satelitarne | Radar VV, VH | Sentinel-1 RTC, Microsoft Planetary Computer | 10 m, od 2017 | Copernicus data policy; RTC: CC BY 4.0 |
| Glebowe | Uziarnienie, węgiel organiczny (5 warstw 0–100 cm) | ISRIC SoilGrids 2.0 | 250 m | CC BY 4.0 |
| Glebowe | Progi suszy dla kategorii gleb i upraw | Rozporządzenie MRiRW, Dz.U. 2019 poz. 739 (metodyka IUNG-PIB) | 4 kategorie gleb, 14 okresów | akt prawny |
| Hydrologiczne | Rowy melioracyjne, cieki (z identyfikatorem MPHP), wody, mokradła, budowle hydrotechniczne | BDOT10k: maski z WMS + atrybuty (GetFeatureInfo) | promień 500 m | dane PZGiK |
| Hydrologiczne | Wody podziemne: punkty monitoringu, stan JCWPd, GZWP | PIG-PIB, Państwowa Służba Hydrogeologiczna (`cbdgmapa.pgi.gov.pl`: `mwp`, `jcwpd`, `gzwp`) | punkty do 15 km od działki | dane publiczne PIG-PIB, z podaniem źródła |
| Hydrologiczne / tło | Wskaźnik suszy CDI | Copernicus EMS, Europejskie Obserwatorium Suszy (WMS) | ok. 5 km, co 10 dni od 2012 | z podaniem źródła |
| Wiedza | Parametry upraw (Kc, korzenie, p), kalendarz dla Polski | FAO-56; `data/water/crops.csv` | 14 upraw | publikacja FAO |
| Wiedza | Reguły rekomendacji i rejestr źródeł naukowych | `data/land/rules.yaml`, `data/land/evidence.md` (FAO-56, IUNG-PIB, NWRM, CDR, POLSA i in.) | – | opracowanie zespołu |

## 5. Dane pobierane na bieżąco i pobrane wcześniej

| Dane | Tryb | Data pobrania |
| :--- | :--- | :--- |
| ULDK, EGiB, Open-Meteo, IMGW-PIB, SoilGrids | na żądanie, przy każdej analizie (z pamięcią podręczną) | data i godzina w sekcji „Źródła danych” raportu |
| Sentinel-2, Landsat, Sentinel-1, NMT, BDOT10k, PIG-PIB, EDO | na żądanie, przy każdej analizie (z pamięcią podręczną) | jw. |
| Kostka ERA5-Land | pobrana wcześniej, aktualizowana codziennie | zakres `2015-01-01` → `[DATA KOŃCA]`, zbudowana `[DATA]`, rozmiar `[GB]`, link do pobrania: `[LINK]` |
| Progi KBW (`data/water/kbw_thresholds.csv`) | przepisane z aktu prawnego | 21.11.2026 |
| Parametry upraw, współrzędne stacji IMGW, fenologia, reguły, rejestr źródeł (`data/`) | przygotowane wcześniej | 21.11.2026 |

**Historia meteo pochodzi z kostki ERA5-Land.** To lokalny plik Zarr z danymi dobowymi dla całej Polski od 2015 r.:

- budowany raz skryptem `scripts.build_era5_cube` z danych godzinowych Copernicus CDS;
- codziennie uzupełniany przez `scripts.update_era5` (usługa `era5-updater` w Docker Compose).

Seria dla działki czyta się z kostki w milisekundach, bez zapytań do zewnętrznego API. Open-Meteo dostarcza tylko:

- ostatnie ok. 5 dni, których ERA5 jeszcze nie opublikował;
- prognozę na 7 dni.

Archiwum Open-Meteo jest wyłącznie zapasem na wypadek braku kostki. Raport pokazuje, z którego źródła pochodzi każdy dzień, a `/api/health` podaje datę końca kostki.

**Wynik i rekomendacje zawsze liczy aplikacja** z tych danych w chwili analizy. Dla daty historycznej używane są wyłącznie dane do tej daty: bez prognozy, bez późniejszych zdjęć i bez późniejszych pomiarów.

## 6. Biblioteki, usługi zewnętrzne i AI

| Komponent | Licencja |
| :--- | :--- |
| FastAPI, Pydantic, pydantic-settings | MIT |
| Uvicorn, httpx | BSD-3-Clause |
| NumPy, pandas, SciPy, Dask | BSD-3-Clause |
| xarray | Apache-2.0 |
| zarr, netCDF4 | MIT |
| Shapely, rasterio (GDAL) | BSD-3-Clause / MIT |
| pyproj, DuckDB | MIT |
| Matplotlib | Matplotlib License (PSF) |
| ReportLab (open source) | BSD |
| PyYAML | MIT |
| anthropic (SDK) | MIT |
| cdsapi | Apache-2.0 |
| pytest, ruff, respx | MIT / BSD-3-Clause |

Żadna biblioteka nie jest na licencji GPL. Usługi zewnętrzne to wyłącznie źródła danych z sekcji 4 oraz Claude API (asystent).

**Sztuczna inteligencja w aplikacji.**

- Asystent „Kolba” korzysta z modelu Claude (Anthropic) przez API. Model ustawia `WODIVA_ASSISTANT_MODEL`, domyślnie `claude-opus-5-5`.
- Model dostaje tylko JSON raportu działki i rejestr źródeł. Ma polecenie odpowiadać wyłącznie na ich podstawie, podawać identyfikator źródła i nie tworzyć nowych liczb.
- Bez `ANTHROPIC_API_KEY` asystent działa w trybie gotowych pytań, bez modelu.
- Ocena, przyczyny, rekomendacje i nawadnianie są liczone deterministycznie, bez AI. Uczenie maszynowe nie jest używane.

**AI przy tworzeniu.** `[uzupełnić: jakie narzędzia AI zespół wykorzystał przy pisaniu kodu i dokumentacji]`

## 7. Licencje, płatne usługi i koszty

- **Dane:** wszystkie są bezpłatne i legalnie dostępne. Licencje są w tabeli w sekcji 4, a każdy raport wymienia je przy źródłach.
- **Open-Meteo:** bezpłatnie tylko do użytku niekomercyjnego. Przy wdrożeniu w KOWR są trzy możliwości:
  - płatny plan Open-Meteo (`OPENMETEO_API_KEY`, cena wg cennika dostawcy);
  - kostka ERA5-Land + IMGW, ale bez prognozy;
  - własna instancja Open-Meteo (kod AGPL, uruchamiany jako osobna usługa).
- **Claude API (asystent):** płatne za użycie. Jedno pytanie to ok. 10 tys. tokenów wejścia i 0,5 tys. tokenów wyjścia, czyli ok. 0,05 USD według cennika `claude-opus-5-5`. Alternatywa bez kosztów: tryb gotowych pytań.
- **CDS (ERA5):** bezpłatne konto i klucz, zlecenia w kolejce.
- **Infrastruktura prototypu:** serwer 2 vCPU / 4 GB RAM / 20 GB dysku, ok. `[KWOTA]` zł miesięcznie.

## 8. Znane ograniczenia

**Meteo i gleba.**

- ERA5-Land ma rozdzielczość ok. 9 km i opóźnienie ok. 5 dni, więc lokalny opad burzowy może się różnić. Walidacja na 22 działkach: mediana różnicy opadu wobec stacji IMGW z 12 miesięcy to 23% (`docs/validation.md`). Raport pokazuje porównanie z najbliższą stacją.
- Kostka ERA5-Land powstaje z danych godzinowych:
  - temperatura maksymalna i minimalna z 8 terminów (co 3 h), co może zaniżać ekstrema o ok. 0,5 °C;
  - punkt rosy, ciśnienie i wiatr z 4 terminów.
- Klimatyczny bilans wodny to opad minus ET0 Penman-Monteith. IUNG-PIB liczy parowanie własną formułą, więc wartości mogą się nieco różnić.
- Mapa kategorii gleb IUNG nie ma publicznego API. Kategorię wyznaczamy z uziarnienia SoilGrids (250 m); użytkownik może podać ją ręcznie (`soil_category`).
- Model wody w glebie:
  - ma jedną warstwę, bez podsiąku z wód gruntowych, śniegu i zamarzania;
  - spływ jest uproszczony;
  - SPI z ok. 10 lat ma ograniczoną dokładność dla wartości skrajnych.

**Satelity.**

- Sentinel-2 ma piksel 10 m, więc działki mniejsze niż ok. 0,3 ha mają niską pewność oceny satelitarnej.
- Porównanie z poprzednimi latami nie uwzględnia zmiany uprawy na działce, a lata z Landsat (30 m) dają porównanie przybliżone.
- Przy zachmurzeniu część lat odniesienia może być niedostępna. Raport podaje, ile lat porównano. Brakujące lata dociągają się w tle i są użyte przy kolejnej analizie tej działki.
- Radar opisuje tylko wierzchnią warstwę gleby i roślinność; świeży opad zaburza sygnał.

**Teren.**

- NMT pobieramy z usługi wysokości GUGiK punkt po punkcie, więc siatka ma 2–6 m zamiast 1 m. Usługa WCS z siatką 1 m odpowiada ok. 60 s na wycinek 200×200 m, za wolno na limit czasu.
- Bruzdy węższe niż oczko siatki są wygładzone.
- Gdy usługa wysokości nie odpowie, używany jest Copernicus DEM 30 m, który pokazuje też roślinność i budynki. Raport oznacza wtedy miejsca retencji jako orientacyjne.

**Hydrologia.**

- Usługi MPHP w Hydroportalu ISOK (Wody Polskie) wymagają autoryzacji (HTTP 401). Cieki i zbiorniki pochodzą więc z BDOT10k, z identyfikatorem MPHP zapisanym w BDOT10k.
- BDOT10k odczytujemy z WMS jako raster z siatką 2,5 m, więc odległości mają dokładność kilku metrów.
- Wody podziemne opisują najbliższe punkty monitoringu PIG-PIB (do 15 km) i ocena JCWPd z 2022 r., nie pomiar na działce.
- PIG-PIB udostępnia tylko ostatni pomiar zwierciadła wody; dla daty historycznej późniejszy pomiar jest pomijany.
- Wskaźnik CDI z EDO opisuje region (ok. 5 km), nie działkę.

**Ogólne.**

- Raport nie zastępuje oględzin pola ani pomiaru wilgotności gleby.
- Nie uwzględnia drenowania, wcześniejszego nawadniania, chorób i szkodników.
- Budowa urządzeń wodnych i pobór wody wymagają uzgodnień według Prawa wodnego.

## 9. Weryfikacja wyników

**Testy automatyczne** (`pytest`, 113 testów, bez sieci):

- **Model wody:**
  - ET0 na przykładzie 18 z FAO-56 (Bruksela, 3,9 mm/d);
  - pedotransfer wobec tabel Saxton i Rawls;
  - bilans masy modelu wody i granice zapasu;
  - zasada „więcej opadu = mniej stresu”;
  - okresy i progi KBW z rozporządzenia;
  - brak danych po dacie analizy.
- **Satelity i teren:**
  - wyostrzanie pasm (odtworzenie pasma i zachowanie średnich 20 m);
  - wagi pikseli (suma równa polu działki);
  - przesunięcie faz uprawy;
  - maska chmur Landsat;
  - analiza terenu na syntetycznym NMT (głębokość i objętość zagłębienia, spadek);
  - pobieranie NMT w porcjach po 1000 punktów.
- **Hydrologia:** atrybuty BDOT10k z identyfikatorem MPHP; PIG-PIB z zasadą daty analizy.
- **Rekomendacje i raport:**
  - kolejność etapów (brak oceny → brak rekomendacji);
  - kompletność tekstów reguł;
  - raport PDF;
  - API raportu i asystenta;
  - pełny przebieg `/api/analyze`.

**Walidacja na działkach z całej Polski** (`scripts/validate.py` → `docs/validation.md`):

- 22 udane analizy z 16 województw dla dat z lat 2017–2024;
- czas: mediana 8,9 s, maksimum 29,2 s, wszystkie poniżej 30 s;
- opad ERA5 porównany z IMGW-PIB;
- susza wg KBW porównana ręcznie z Systemem Monitoringu Suszy Rolniczej IUNG-PIB.

**Kontrola części satelitarno-terenowej na żywych danych** (21.11.2026, Strzelno 0,9 ha i Narol 16,9 ha):

- czas: 17–19 s;
- NMT w siatce 3 m i 6 m z pełnym pokryciem;
- średni spadek 1,8% (Kujawy) i 11,6% (Roztocze);
- cieki z identyfikatorami MPHP 188174 i 2282744;
- JCWPd PLGW600043 ze słabym stanem ilościowym, zgodnie z oceną PIG-PIB 2022.

**Kontrola krzyżowa w każdym raporcie.** Bilans wodny jest pokazany obok trzech niezależnych sygnałów:

- stanu roślin z satelity;
- radaru;
- wskaźnika CDI z EDO.

Rozbieżności widać od razu, a każda część raportu ma ocenę pewności z uzasadnieniem.

## 10. Skalowalność

- **Limity zewnętrznych źródeł:**
  - pamięć podręczna z czasem ważności zależnym od źródła (gleba 1 rok, działka i model terenu 30 dni, meteo bieżące 3 h, wyszukiwania zdjęć satelitarnych do 30 dni);
  - Open-Meteo buforowane na komórkę siatki 0,1° i dzień, więc jedno zapytanie obsługuje wszystkich użytkowników z komórki;
  - limit zapytań na adres IP (`RATE_LIMIT_PER_MINUTE`, domyślnie 30).
- **Aktualizacja danych:**
  - kostka ERA5-Land codziennie;
  - pozostałe źródła przy każdej analizie, z pamięcią podręczną;
  - dane z tej samej sceny satelitarnej lub tego samego fragmentu terenu nie są pobierane ponownie.
- **Szybkość:**
  - historia meteo czytana lokalnie z kostki;
  - źródła pobierane równolegle, każde z własnym limitem czasu;
  - przy wielu użytkownikach: kilka instancji backendu za load balancerem, wspólna pamięć podręczna (Redis lub magazyn obiektowy zamiast SQLite), kostka ERA5 w magazynie obiektowym (S3).
- **Koszty przy rozwoju:**
  - serwery aplikacji i magazyn danych;
  - plan Open-Meteo przy użyciu komercyjnym;
  - Claude API proporcjonalnie do liczby pytań do asystenta;
  - źródła publiczne (GUGiK, PIG-PIB, Copernicus, IMGW) są bezpłatne.

## 11. Bezpieczeństwo

- Brak kont użytkowników i danych osobowych. ULDK zwraca tylko geometrię i identyfikator działki, bez danych właściciela.
- Walidacja wejścia: format identyfikatora działki, zakres daty (ostatnie 10 lat, nie z przyszłości), lista upraw, format identyfikatora raportu.
- Limit zapytań na IP dla analizy, wyszukiwania działki i asystenta.
- Klucze (`CDSAPI_KEY`, `ANTHROPIC_API_KEY`, `OPENMETEO_API_KEY`) tylko w `.env` na serwerze. Do repozytorium trafia `.env.example`.
- Nagłówki `X-Content-Type-Options` i `Referrer-Policy`. Dozwolone adresy interfejsu (CORS) ustawia `CORS_ORIGINS`; w środowisku produkcyjnym należy tam wpisać adres interfejsu zamiast domyślnego `*`.
- Kontener działa na użytkowniku bez uprawnień administratora.

## Do uzupełnienia przed zgłoszeniem

- [ ] Nazwa zespołu (bez imion i nazwisk) i linki w tabeli na początku.
- [ ] Sekcja 5: zakres, data zbudowania, rozmiar i link do kostki ERA5-Land.
- [ ] Sekcja 6: narzędzia AI użyte przy tworzeniu.
- [ ] Sekcja 7: miesięczny koszt serwera.
- [ ] `docs/raporty/`: kilka raportów PDF wygenerowanych przez prototyp.
