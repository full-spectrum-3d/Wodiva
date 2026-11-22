# Wodiva – asystent wody dla działki rolnej

HackNation 2026 · zadanie KOWR „Zatrzymaj wodę, chroń plony” · zespół **Full Spectrum 3D**

| Materiał zgłoszenia | Gdzie |
| :--- | :--- |
| Działająca wersja | `[LINK DO APLIKACJI]` |
| Instrukcja uruchomienia | [sekcja 1](#1-uruchomienie) |
| Repozytorium (prywatne) | https://github.com/full-spectrum-3d/Wodiva |
| Prezentacja PDF (do 10 slajdów) | `[LINK DO PREZENTACJI]` |
| Film z działania (do 3 min) | `[LINK DO FILMU]` |
| Raporty wygenerowane przez prototyp | `docs/raporty/` |

## Opis rozwiązania

**Problem.** Dane o wodzie są rozproszone w kilkunastu serwisach: IMGW, Copernicus, GUGiK, PIG-PIB, IUNG i Wody Polskie. Każdy ma inny format. Rolnik bez znajomości GIS nie sprawdzi w nich, czy jego działka jest sucha, dlaczego i co z tym zrobić.

**Główne funkcjonalności.**

1. Rolnik wskazuje działkę na jeden z czterech sposobów: numerem ewidencyjnym, adresem domu, gminą z obrębem i numerem albo kliknięciem na mapie. Potem wybiera uprawę i datę analizy.
2. Aplikacja ocenia wodę na działce. Liczy obecny zapas wody w glebie i to, jak często działka miała niedobór w ostatnich 10 latach.
3. Pokazuje przyczyny niedoboru w milimetrach wody.
4. Podaje rekomendacje w kolejności KOWR: retencja, potem agrotechnika, potem nawadnianie. Miejsca do zatrzymania wody zaznacza na mapie działki.
5. Raport zostaje zapisany pod stałym linkiem. Można go pobrać jako PDF albo wydrukować.
6. Asystent „Kolba” odpowiada na pytania rolnika o jego raport.

**Sposób wykorzystania danych.** Przy każdej analizie aplikacja pobiera dane z pięciu kategorii: meteorologiczne, satelitarne, glebowe, hydrologiczne i przestrzenne. Z nich liczy wynik deterministycznym kodem: FAO-56, klimatyczny bilans wodny, wskaźniki Sentinel-2, analizę NMT i reguły rekomendacji. Model językowy nie liczy wyników. Raport wymienia każde źródło z datą pobrania, licencją i statusem (ok, częściowo, brak).

**Korzyści dla rolnika.**

- Dostaje konkretne działania z liczbami dla swojej działki, np. „zastawka na rowie 60 m od działki” albo „międzyplon: 7 dni stresu wodnego mniej w 2019 r.”.
- Widzi kalendarz ryzyka suszy w dekadach.
- Wie, czy i kiedy nawadniać oraz jaką dawką. Dostaje też informację o zgłoszeniu lub pozwoleniu wodnoprawnym.
- Zalecenia są powiązane z ekoschematami WPR.
- Raport wprost mówi, czego brakuje w danych i jak pewny jest wynik.
- Nie trzeba znać GIS, niczego instalować ani płacić.

## Zgodność z wymaganiami

| Wymaganie KOWR | Realizacja |
| :--- | :--- |
| 3.2 Aplikacja w przeglądarce, bez instalacji; telefon jako atut | interfejs webowy (Angular), układ od szerokości telefonu, WCAG 2.1 AA |
| 3.3.2 Działka z numeru lub z mapy, dowolna w Polsce | `GET /api/parcel?id=` lub `?lat=&lon=`, `/api/parcel/region` (gmina, obręb, numer), `/api/parcel/address` (adres); źródła: lokalny indeks EGiB, potem ULDK, potem eksport EGiB z Geoportalu |
| 3.3.3 Wybór uprawy | 14 upraw (`GET /api/crops`) |
| 3.2 pkt 1 i 3.3.4 Ocena stanu wilgotności, bieżąca i z 10 lat | bilans wody w glebie FAO-56, KBW, SPI, percentyl wobec tej samej daty w 10 latach, stan roślin wobec 9 poprzednich lat |
| 3.2 pkt 1a Interpretacja satelitarna zależna od uprawy | fazy rozwoju upraw: niski NDVI po zbiorze lub przed siewem nie jest liczony jako susza |
| 3.2 pkt 2 Retencja i agrotechnika z terenu i hydrologii | zagłębienia i linie spływu z NMT; rowy, cieki, zbiorniki i mokradła z BDOT10k; wody podziemne z PIG-PIB |
| 3.2 pkt 3 Nawadnianie (opcjonalne) | zasadność, termin z prognozą 7 dni, dawka netto i brutto, objętość wody |
| Kolejność etapów | wymuszona w kodzie: bez oceny wody raport nie ma przyczyn ani rekomendacji |
| 3.3.4 Wynik liczony z pobranych danych | wszystko jest liczone przy każdej analizie; reguły rekomendacji wypełniają się liczbami działki |
| 3.3.5 Zawartość raportu | ocena, przyczyny, rekomendacje z uzasadnieniem i źródłami, data, źródła, ograniczenia, pewność, braki danych |
| 3.3.6 Zapis, PDF, druk | `/api/report/{id}`, `/api/report/{id}.pdf` (mapa i kod QR), przycisk druku |
| 3.3 Pięć kategorii danych | [sekcja 4](#4-źródła-i-zakresy-danych) |
| 6 Dowolna data z 10 lat | dla daty historycznej używane są tylko dane do tej daty (testy `test_date_rule.py`) |
| 7.5 Wynik w 30 s | mediana 6,9 s, maksimum 13,0 s ([sekcja 9](#9-weryfikacja-wyników)) |
| 4.2 pkt 1–9 | sekcje 1–9 |
| 5.1 Zakres użycia AI | [sekcja 6](#6-biblioteki-usługi-i-ai) |
| 5.4 Bez płatnej licencji; płatne opcje z kosztami | [sekcja 7](#7-licencje-płatne-usługi-i-koszty) |
| 5.5 Skalowalność | [sekcja 10](#10-skalowalność) |
| 5.6 Bezpieczeństwo, brak danych osobowych | [sekcja 11](#11-bezpieczeństwo) |

## 1. Uruchomienie

### Docker (zalecane)

```bash
git lfs pull
cp .env.example .env
docker compose up --build -d
```

- Aplikacja działa pod `http://localhost:8080`, a dokumentacja API pod `http://localhost:8000/docs`.
- Przy pierwszym starcie usługa `ollama-pull` pobiera model asystenta, około 5 GB. Do tego czasu Kolba odpowiada z raportu bez modelu.
- Kostka ERA5-Land jest aktualizowana codziennie: `docker compose --profile era5 up -d era5-updater`.

### GitHub Codespaces

Otwórz repozytorium w Codespaces i uruchom `bash start-codespace.sh`. Skrypt podaje adres aplikacji (port 4200).

### Bez Dockera

Wymagania: Python 3.12, Node 24.15 lub nowszy i Git LFS.

**Backend.** Na Windows środowisko aktywujesz poleceniem `.venv\Scripts\Activate.ps1`.

```bash
cp .env.example .env
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,era5]"
python -c "import duckdb; duckdb.connect().execute('INSTALL httpfs')"
uvicorn app.core.main:app --port 8000
```

**Interfejs** (w drugim terminalu):

```bash
cd frontend
npm ci
npx ng serve
```

Interfejs działa pod `http://localhost:4200` i przekazuje `/api` do portu 8000.

### Dane przygotowane wcześniej

**Kostka ERA5-Land** (historia meteo, 01.01.2006–15.11.2026) jest w Git LFS (`backend/data/era5_land_pl.tar.gz`, ok. 1 GB). Rozpakuj ją z katalogu głównego repozytorium; trwa to ok. 1,5 min:

```bash
git lfs install
git lfs pull --include "backend/data/era5_land_pl.tar.gz"
mkdir -p backend/var
tar xzf backend/data/era5_land_pl.tar.gz -C backend/var
```

- Kostka trafi do `backend/var/era5_land_pl.zarr`, czyli tam, gdzie szuka jej backend.
- Jeśli archiwum ma tylko kilkaset bajtów, LFS go nie pobrał. Uruchom wtedy dwie pierwsze linijki.
- Bez kostki aplikacja bierze historię meteo z archiwum Open-Meteo, co trwa dłużej.

Kostkę można też zbudować od zera. Wymaga to `CDSAPI_KEY`:

```bash
python -m scripts.build_era5_cube --start 2006-01-01
python -m scripts.update_era5
```

**Lokalny indeks działek EGiB** jest opcjonalny. Odciąża ULDK, a bez niego aplikacja korzysta z ULDK. Polecenia uruchom z katalogu głównego repozytorium:

```bash
python backend/scripts/dzialki_index.py --plik data/dzialki.parquet --indeks data/dzialki_indeks pobierz
python backend/scripts/dzialki_index.py --plik data/dzialki.parquet --indeks data/dzialki_indeks indeks
```

- Polecenie `pobierz` ściąga eksport `0_dzialki.parquet` z Geoportalu (4,6 GB, ok. 38,9 mln działek).
- Polecenie `indeks` dzieli eksport na 16 plików województw posortowanych po identyfikatorze działki.
- Docker podłącza `./data/dzialki_indeks` automatycznie. Bez Dockera ustaw w `.env` zmienną `WODIVA_PARCELS_INDEX_DIR` na pełną ścieżkę do tego katalogu.

### Szybki test

```bash
curl -X POST http://localhost:8000/api/analyze -H "Content-Type: application/json" \
  -d '{"parcel_id":"040904_5.0023.248","date":"2025-07-15","crop":"kukurydza_ziarno"}'
```

Z odpowiedzi weź `id` i otwórz `http://localhost:8000/api/report/{id}.pdf`. Parametr `?mock=true` daje raport na danych syntetycznych, bez internetu.

## 2. Funkcjonalności

**Interfejs.**

- Kreator ma trzy kroki: działka, data, uprawa. Obok jest mapa.
- Działkę można znaleźć na cztery sposoby:
  - **Numer działki:** pełny identyfikator albo skrót „gmina, obręb numer”, np. `Bogatynia, Krzewina 134`.
  - **Adres:** miejscowość, ulica i numer domu. Aplikacja znajduje działkę, na której stoi budynek. Pole obok wybiera się potem na mapie.
  - **Gmina i obręb:** trzy osobne pola, tak jak w wypisie z ewidencji albo we wniosku o dopłaty.
  - **Kliknięcie na mapie.**
- Gdy pasuje kilka działek, aplikacja pokazuje listę do wyboru.
- Mapa pokazuje granice i numery działek oraz użytki gruntowe z klasami gleb z EGiB, z legendą skrótów (R, Ł, Ps, S…).
- Każdą mapę można otworzyć na pełnym ekranie.
- Opcja „Tylko działki rolne” jest domyślnie włączona. Blokuje analizę gruntu nierolniczego i działki, której użytku ewidencja nie podaje.
- Podkłady mapy: OpenStreetMap, ortofotomapa GUGiK i cieniowany model terenu GUGiK.
- Raport ma zakładki w kolejności KOWR: ocena, przyczyny, retencja, agrotechnika, nawadnianie, źródła.
- Mapa raportu pokazuje:
  - granicę działki i strefę 500 m;
  - zagłębienia i linie spływu;
  - rowy, cieki, zbiorniki i punkty wód podziemnych;
  - miejsca rekomendacji.
- Mapa raportu ma 6 nakładek z legendą: NDVI, NDMI, NDWI, NDRE, spadek terenu i TWI.
- Identyfikatory źródeł naukowych (E01–E23) w tekście raportu otwierają ich opis.
- Raport można pobrać jako PDF i wydrukować. Asystent Kolba jest dostępny z poziomu raportu.

**Etap 1. Ocena stanu wilgotności.**

- Meteo:
  - dane dobowe z ERA5-Land, a ostatnie dni i prognoza na 7 dni z Open-Meteo;
  - kontrola z najbliższą stacją synoptyczną IMGW-PIB;
  - ET0 liczone metodą FAO-56 Penman-Monteith.
- Klimatyczny bilans wodny w okresach sześciodekadowych, z progami suszy z rozporządzenia MRiRW (Dz.U. 2019 poz. 739). Ta sama metoda co w systemie IUNG-PIB.
- Wskaźniki: SPI (1 i 3 mies.), anomalia ET0, dni upalne i okresy bez opadu.
- Gleba:
  - z SoilGrids, 5 warstw do 100 cm;
  - przeliczana na pojemność wodną (Saxton i Rawls 2006);
  - przypisywana do kategorii podatności na suszę IUNG.
- Dobowy bilans wody w glebie FAO-56 dla wybranej uprawy: zapas, dni stresu, percentyl wobec tej samej daty w 10 latach i kalendarz ryzyka.
- Sentinel-2:
  - wskaźniki NDVI, NDMI, NDWI i NDRE z maską chmur, ważone udziałem piksela w działce;
  - stan roślin porównany z 9 poprzednimi latami (VCI), a brakujące lata uzupełnia Landsat.
- Sentinel-1 (radar) i wskaźnik suszy CDI z EDO jako sygnały kontrolne.

**Etap 2. Przyczyny i rekomendacje.**

- Przyczyny mają wkład w mm:
  - niedobór opadów;
  - upał i parowanie;
  - mała pojemność wodna gleby;
  - odpływ powierzchniowy;
  - brak retencji w otoczeniu.
- Retencja, na podstawie NMT (siatka 2–6 m) i BDOT10k:
  - zagłębienia z powierzchnią i objętością;
  - pasy buforowe na liniach spływu;
  - zastawki na rowach, z informacją o Prawie wodnym;
  - strefy buforowe przy ciekach;
  - priorytet retencji tam, gdzie wody podziemne są w słabym stanie.
- Agrotechnika:
  - zabiegi: międzyplony, materia organiczna, uprawa uproszczona i mulcz, uprawa w poprzek stoku, dobór odmian;
  - symulacje „co jeśli” dla tej działki;
  - powiązania z ekoschematami.

**Etap 3. Nawadnianie.** Aplikacja ocenia, czy nawadniać, i podaje termin z prognozą opadu, dawkę netto i brutto oraz objętość wody.

**Asystent Kolba.** Odpowiada po polsku na pytania o raport. Fakty o działce bierze tylko z raportu. W sprawach przepisów i dopłat odsyła do stron urzędowych: ARiMR, Wody Polskie, IMGW, IUNG, MRiRW i ODR.

## 3. Architektura

```
przeglądarka ── Angular 22 + Leaflet (frontend/) ── nginx ── /api ── FastAPI (backend/)

POST /api/analyze
  ├─ water.parcel       działka: indeks EGiB → ULDK → eksport EGiB; adres → UUG → punkt; użytki EGiB
  ├─ równolegle:
  │    water.prepare    meteo (ERA5 + Open-Meteo + IMGW), gleba (SoilGrids, IUNG)
  │    land.observe     Sentinel-2, Landsat, Sentinel-1, NMT, BDOT10k, PIG-PIB, EDO (limit 20 s)
  ├─ water.compute      KBW, wskaźniki, bilans FAO-56, scenariusze, nawadnianie
  ├─ land.interpret     ocena, przyczyny, rekomendacje, pewność
  └─ report.build       raport JSON → SQLite → PDF, mapa, nakładki
```

- **Moduły.** `water/` obejmuje działkę, meteo, glebę i model wody. `land/` obejmuje satelity, teren, hydrologię i rekomendacje. `report/` i `assistant/` to raport i Kolba. `water/` i `land/` nie importują się nawzajem: wymieniają dane przez `core/schemas.py`.
- **Interfejs** niczego nie liczy, tylko wyświetla raport JSON.
- **Pamięć podręczna** jest w SQLite, z czasem ważności dla każdego źródła. Raporty też są w SQLite.
- **Pobieranie danych.** Każde źródło ma własny limit czasu i ponawianie, a czas każdego trafia do `timings_s` w raporcie.

## 4. Źródła i zakresy danych

| Kategoria | Dane | Źródło | Zakres | Licencja |
| :--- | :--- | :--- | :--- | :--- |
| Przestrzenne | Granica i identyfikator działki | ULDK GUGiK; eksport EGiB `0_dzialki.parquet` (Geoportal opendata) | cała Polska | dane PZGiK, bezpłatne |
| Przestrzenne | Położenie adresu (wyszukiwanie po adresie) | UUG GUGiK – usługa geokodowania (PRG) | cała Polska | dane PZGiK, bezpłatne |
| Przestrzenne | Użytki gruntowe | EGiB: klasoużytki z eksportu, WMS KIEG | cała Polska | dane PZGiK |
| Przestrzenne | Rzeźba terenu | NMT GUGiK (usługa wysokości); zapas Copernicus DEM GLO-30 | siatka 2–6 m; zapas 30 m | dane PZGiK; Copernicus DEM z podaniem źródła |
| Przestrzenne | Pokrycie terenu | BDOT10k (WMS Geoportalu) | 500 m od działki | dane PZGiK |
| Meteorologiczne | Opad, temperatura, punkt rosy, wiatr, promieniowanie, ciśnienie | ERA5-Land, Copernicus C3S | 0,1°, od 2006 r. | Licence to use Copernicus Products |
| Meteorologiczne | Ostatnie dni i prognoza 7 dni | Open-Meteo | 0,1° | CC BY 4.0, bezpłatnie niekomercyjnie |
| Meteorologiczne | Pomiar kontrolny | IMGW-PIB, dane synoptyczne | najbliższa stacja | dane publiczne, z podaniem źródła |
| Satelitarne | NDVI, NDMI, NDWI, NDRE | Sentinel-2 L2A, Earth Search (AWS) | 10 m, od 07.2015 | Copernicus data policy |
| Satelitarne | Lata bez Sentinel-2 | Landsat 5/7/8/9 C2 L2, Planetary Computer | 30 m | USGS, domena publiczna |
| Satelitarne | Radar VV, VH | Sentinel-1 RTC, Planetary Computer | 10 m, od 2017 | Copernicus; RTC CC BY 4.0 |
| Glebowe | Uziarnienie, węgiel organiczny | ISRIC SoilGrids 2.0 | 250 m, 0–100 cm | CC BY 4.0 |
| Glebowe | Progi suszy dla gleb i upraw | Dz.U. 2019 poz. 739 (metodyka IUNG-PIB) | 4 kategorie gleb | akt prawny |
| Hydrologiczne | Rowy, cieki z identyfikatorem MPHP, zbiorniki, mokradła | BDOT10k (WMS i GetFeatureInfo) | 500 m od działki | dane PZGiK |
| Hydrologiczne | Wody podziemne: monitoring, stan JCWPd, GZWP | PIG-PIB (`cbdgmapa.pgi.gov.pl`) | do 15 km od działki | dane publiczne, z podaniem źródła |
| Tło suszowe | Wskaźnik CDI | Copernicus EMS – EDO (WMS) | ok. 5 km, co 10 dni od 2012 | z podaniem źródła |
| Wiedza | Parametry upraw | FAO-56 (`data/water/crops.csv`) | 14 upraw | publikacja FAO |
| Wiedza | Reguły rekomendacji i źródła naukowe | `data/land/rules.yaml`, `data/land/evidence.md` (E01–E23) | – | opracowanie zespołu |

## 5. Dane pobierane na bieżąco i pobrane wcześniej

| Dane | Tryb | Data pobrania |
| :--- | :--- | :--- |
| ULDK, UUG, KIEG, Open-Meteo, IMGW-PIB, SoilGrids, Sentinel-2, Landsat, Sentinel-1, NMT, BDOT10k, PIG-PIB, EDO | pobierane przy każdej analizie, z pamięcią podręczną | data i godzina przy każdym źródle w raporcie |
| Kostka ERA5-Land (`backend/data/era5_land_pl.tar.gz`) | pobrana wcześniej z Copernicus CDS, aktualizowana codziennie przez `update_era5` | pobrana 21–22.11.2026; zakres 01.01.2006–15.11.2026 (7624 dni); aktualny koniec: `GET /api/health` |
| Indeks działek EGiB (`data/dzialki_indeks/`, opcjonalny) | pobrany wcześniej z Geoportalu skryptem `dzialki_index.py` | data eksportu przy źródle „EGiB – lokalny indeks” w raporcie |
| Progi KBW, parametry upraw, stacje IMGW, fenologia, reguły, rejestr źródeł (`backend/data/`) | przygotowane wcześniej przez zespół | 21.11.2026 |

Wynik i rekomendacje zawsze liczy aplikacja, z tych danych, w chwili analizy. Dla daty historycznej bierze tylko dane do tej daty: bez prognozy, bez późniejszych zdjęć i bez późniejszych pomiarów.

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
| Matplotlib | PSF (Matplotlib License) |
| ReportLab | BSD |
| PyYAML | MIT |
| anthropic SDK (opcjonalny dostawca asystenta), cdsapi | MIT, Apache-2.0 |
| pytest, ruff, respx | MIT |
| Angular, RxJS, TypeScript | MIT, Apache-2.0 |
| Tailwind CSS, Vitest, Prettier | MIT |
| Leaflet | BSD-2-Clause |
| Czcionki Urbanist, Atkinson Hyperlegible | SIL OFL 1.1 |
| nginx | BSD-2-Clause |
| Ollama | MIT |
| Model Bielik 4.5B v3.0 Instruct (SpeakLeash) | Apache-2.0 |

Żadna biblioteka nie jest na licencji GPL.

**AI w aplikacji.**

- Kolba korzysta z modelu Bielik 4.5B uruchomionego lokalnie w Ollama (`WODIVA_ASSISTANT_PROVIDER=ollama`). Model jest bezpłatny i polski, a dane nie wychodzą poza serwer.
- Model dostaje skrócone fakty z raportu i kilka ostatnich wiadomości rozmowy. Nie liczy nowych wyników. Odpowiada krótko, do 250 tokenów, przy kontekście 3072 tokenów.
- Backend ładuje model do pamięci przy starcie i trzyma go tam przez 2 godziny (`keep_alive`). Po otwarciu okna Kolby przygotowuje model dla danego raportu (`POST /api/assistant/prepare`), więc pierwsza odpowiedź przychodzi szybciej.
- Gdy model jest niedostępny, Kolba odpowiada bez modelu, regułami z raportu: o przyczynach, pierwszych krokach, nawadnianiu, retencji, glebie, opadach, satelicie, wodach podziemnych, dopłatach i pozwoleniach.
- Opcjonalnie można włączyć Claude API (`WODIVA_ASSISTANT_PROVIDER=anthropic` i `ANTHROPIC_API_KEY`). To usługa płatna, opisana w sekcji 7.
- Ocena, przyczyny, rekomendacje i nawadnianie są liczone bez AI. Uczenie maszynowe nie jest używane.

**AI przy tworzeniu.** Zespół korzystał z Claude (Anthropic) przy pisaniu kodu, testów i dokumentacji. Każdą zmianę zespół przeglądał i sprawdzał testami. Prawa do treści wygenerowanych przez model przysługują użytkownikowi, więc nie ograniczają przeniesienia praw na KOWR.

## 7. Licencje, płatne usługi i koszty

- **Dla rolnika** wszystko jest bezpłatne: bez licencji, bez konta i bez instalacji.
- **Dane** są publiczne i bezpłatne. Raport podaje źródło i licencję każdej pozycji.
- **Open-Meteo** jest bezpłatne tylko do użytku niekomercyjnego. Przy wdrożeniu są trzy możliwości:
  - płatny plan (`OPENMETEO_API_KEY`);
  - kostka ERA5 z IMGW, ale bez prognozy;
  - własna instancja Open-Meteo.
- **Asystent** w domyślnej konfiguracji nic nie kosztuje: działa na lokalnym modelu, a awaryjnie bez modelu. Claude API jest opcją płatną za użycie, według cennika Anthropic. Jedno pytanie zużywa ok. 10 tys. tokenów wejścia i 1–2 tys. tokenów wyjścia.
- **CDS (ERA5)** wymaga bezpłatnego konta.
- **Serwer prototypu** to 8 vCPU, 16 GB RAM i ok. 80 GB dysku. Mieści backend, interfejs, model Bielik na CPU, kostkę ERA5 i indeks działek. Koszt to orientacyjnie 100–200 zł miesięcznie (VPS w UE). Szybsze odpowiedzi asystenta daje serwer z GPU, który kosztuje od kilkuset zł miesięcznie wzwyż.
- **Usługi pomocnicze interfejsu** mają ograniczenia:
  - Kafelki OpenStreetMap: dane na licencji ODbL, serwer według Tile Usage Policy, nie do dużego ruchu.
  - Google Fonts: przeglądarka łączy się z Google. Przy wdrożeniu czcionki można dołączyć do aplikacji.
- **Przeniesienie praw na KOWR** (regulamin §2 ust. 10 i §5):
  - Kod jest autorstwa zespołu.
  - Biblioteki i model mają licencje permisywne: MIT, BSD, Apache-2.0 i PSF.
  - Kod Open-Meteo (AGPL) nie jest częścią rozwiązania, bo korzystamy tylko z jego API.

## 8. Znane ograniczenia

- **Meteo:**
  - ERA5-Land ma rozdzielczość ok. 9 km i opóźnienie ok. 5 dni, więc lokalne burze mogą się różnić. Mediana różnicy opadu wobec IMGW z 12 miesięcy wynosi 28%.
  - Ekstrema temperatury liczymy z 8 terminów na dobę, więc mogą być zaniżone o ok. 0,5 °C.
- **Gleba:**
  - Kategoria gleby IUNG pochodzi z uziarnienia SoilGrids (250 m), bo mapa IUNG nie ma API. Można ją podać ręcznie (`soil_category`).
  - Model wody ma jedną warstwę. Nie uwzględnia podsiąku, śniegu ani zamarzania.
- **Satelity:**
  - Piksel ma 10 m, więc działka poniżej ok. 0,3 ha ma niską pewność oceny.
  - Porównanie z poprzednimi latami nie uwzględnia zmiany uprawy.
  - Przy zachmurzeniu porównanie obejmuje mniej lat, a raport podaje ile.
- **Teren:**
  - NMT ma siatkę 2–6 m zamiast 1 m, bo usługa WCS jest za wolna na limit 30 s.
  - Przy awarii NMT używamy DEM 30 m, a miejsca retencji są wtedy orientacyjne.
- **Hydrologia:**
  - Usługi MPHP w Hydroportalu wymagają autoryzacji, więc cieki pochodzą z BDOT10k.
  - Wody podziemne opisują punkty monitoringu do 15 km od działki, nie pomiar na działce.
  - CDI z EDO opisuje region, nie działkę.
- **Działki:**
  - Wyszukiwanie po adresie znajduje działkę z budynkiem. Pole uprawne bywa obok, więc wtedy trzeba je kliknąć na mapie.
  - Indeks EGiB jest aktualny na dzień pobrania. Działek spoza indeksu aplikacja szuka w ULDK.
  - Udziały klasoużytków z indeksu są przybliżone, bo eksport nie podaje ich powierzchni.
- **Asystent:**
  - Mały lokalny model może się mylić w wiedzy ogólnej. Liczby o działce bierze z raportu.
  - Na serwerze bez GPU odpowiedź trwa do kilkudziesięciu sekund. Po 150 s Kolba odpowiada bez modelu.
- **Ogólne:**
  - Raport nie zastępuje oględzin pola.
  - Nie uwzględnia drenowania, wcześniejszego nawadniania, chorób ani szkodników.
  - Urządzenia wodne i pobór wody wymagają uzgodnień według Prawa wodnego.

## 9. Weryfikacja wyników

- **Testy automatyczne** (`cd backend && pytest`): 173 testy, bez sieci. Obejmują:
  - ET0 na przykładzie 18 z FAO-56;
  - pedotransfer wobec tabel Saxton i Rawls;
  - bilans masy modelu wody;
  - progi KBW z rozporządzenia;
  - zasadę daty analizy;
  - wyostrzanie pasm Sentinel-2 i wagi pikseli;
  - analizę terenu na syntetycznym NMT;
  - kolejność etapów;
  - rekomendacje zależne od uprawy (łąki bez orki i międzyplonów) i ocena ryzyka poza okresem wegetacji;
  - PDF;
  - API;
  - indeks działek.
- **Testy interfejsu** (`cd frontend && npx ng test`): 56 testów.
- **Walidacja na prawdziwych działkach** (`python -m scripts.validate`, wynik w `docs/validation.md`):
  - 25 analiz, 20 działek z 16 województw, daty z lat 2017–2024 i 21.11.2026;
  - wszystkie analizy zakończone; czas: mediana 6,9 s, maksimum 13,0 s;
  - opad ERA5 porównany z IMGW-PIB;
  - susza według KBW porównana ręcznie z Systemem Monitoringu Suszy Rolniczej IUNG-PIB.
- **Kontrola w każdym raporcie.** Bilans wody jest pokazany obok trzech niezależnych sygnałów: stanu roślin z satelity, radaru i CDI z EDO. Każda część raportu ma ocenę pewności z uzasadnieniem.
- **Dostępność źródeł:** `python -m scripts.smoke_sources`.

## 10. Skalowalność

- **Limity zewnętrznych źródeł:**
  - Pamięć podręczna ma czas ważności zależny od źródła: gleba rok, działka i teren 30 dni, meteo bieżące 3 h.
  - Open-Meteo jest buforowane na komórkę 0,1°, więc jedno zapytanie obsługuje wszystkie działki w tej komórce.
  - Historia meteo i działki są czytane z lokalnych plików (kostka ERA5, indeks EGiB), bez zapytań do API.
  - Limit to 30 zapytań na minutę z jednego adresu IP.
- **Aktualizacja danych:**
  - Kostka ERA5 aktualizuje się codziennie.
  - Indeks EGiB warto odświeżać co tydzień: `pobierz`, a potem `indeks`.
  - Pozostałe źródła są pobierane przy analizie.
- **Większy ruch:**
  - kilka instancji backendu za load balancerem;
  - wspólna pamięć podręczna (Redis);
  - kostka i indeks w magazynie obiektowym (S3);
  - Ollama na serwerze z GPU.
- **Koszty przy rozwoju:**
  - serwery i magazyn danych;
  - GPU dla asystenta przy wielu rozmowach;
  - plan Open-Meteo przy użyciu komercyjnym.
  - Źródła publiczne pozostają bezpłatne.

## 11. Bezpieczeństwo

- Aplikacja nie ma kont użytkowników i nie zbiera danych osobowych. ULDK i EGiB zwracają tylko geometrię, identyfikator i użytki działki, bez danych właściciela.
- Dane wejściowe są walidowane: format identyfikatora, zakres daty (ostatnie 10 lat, nie z przyszłości), lista upraw i identyfikator raportu. Adres, gmina i obręb mają ograniczoną długość i nie mogą zawierać znaków specjalnych.
- Limity zapytań:
  - limit na IP dla analizy, wyszukiwania i asystenta;
  - dzienny limit pytań do asystenta i limit na jeden raport;
  - historia rozmowy podpisana HMAC.
- Klucze są tylko w `.env` na serwerze, a do repozytorium trafia `.env.example`.
- Backend jest dostępny tylko przez nginx, bo port 8000 jest otwarty wyłącznie na localhost. CORS jest domyślnie wyłączony.
- Odpowiedzi mają nagłówki `X-Content-Type-Options` i `Referrer-Policy`. Kontener działa na użytkowniku bez uprawnień administratora.
- Raporty starsze niż 90 dni są usuwane automatycznie.
