# DESIGN.md — Wodiva

Jedyne źródło prawdy o wyglądzie aplikacji. Kolory, fonty, odstępy, promienie i cienie bierzemy wyłącznie stąd (w kodzie: `@theme` Tailwind v4 + CSS custom properties w `frontend/src/styles.css`; domyślne palety, fonty, promienie i breakpointy Tailwinda są wyłączone). Nowa wartość = najpierw dopisz ją tutaj z uzasadnieniem.

---

## 1. Kierunek wizualny: „Wodowskaz i zeszyt polowy”

**Dla kogo:** rolnik bez wiedzy GIS, często na telefonie, na polu, w pełnym słońcu, czasem w rękawicach. Druga grupa: jury KOWR, które uruchamia aplikację na komputerze i porównuje wynik z danymi referencyjnymi.

**Metafora:** wydrukowany biuletyn agrometeorologiczny i łata wodowskazu (podziałka poziomu wody na rzece). Papierowe, ciepłe tło, ciemny „atramentowy” tekst, jeden kolor wody jako akcent, podziałki i linie zamiast kart z cieniami. Raport ma czytać się jak dokument, który można wydrukować i położyć na stole w biurze ODR, a nie jak panel SaaS.

**Zasady:**
1. **Odpowiedź najpierw.** Na górze raportu jedno zdanie oceny (np. „Na działce występuje podwyższone ryzyko suszy rolniczej.”) i wskaźnik zapasu wody. Szczegóły niżej.
2. **Kolejność KOWR widoczna w układzie.** Raport to numerowana sekwencja 1–5: Ocena → Przyczyny → Retencja → Agrotechnika → Nawadnianie. Numeracja jest stałym elementem wizualnym (oś po lewej na desktopie, numery przy nagłówkach na telefonie).
3. **Brak danych mówimy wprost.** Pusta sekcja nie znika: dostaje stan „Brak oceny” / „Nie dotyczy” z powodem. Bez pozornej precyzji: liczby zaokrąglone tak, jak podaje silnik, z jednostką i źródłem.
4. **Kontrast na słońce.** Tekst główny ≥ 15:1, tekst pomocniczy ≥ 7:1 (AAA), elementy UI ≥ 3:1. Bazowy rozmiar tekstu 18 px.
5. **Spokój.** Kolor niesie znaczenie (stan wody), nie dekoruje. Jedna dominująca akcja na ekran.

**Sygnaturowy element — Wodowskaz:** pionowa (desktop) lub pozioma (telefon) podziałka 0–100% zapasu wody dostępnej dla roślin (`soil_water.available_pct`) z kreskami progów 30% i 50% (progi z `backend/app/land/assessment.py`), znacznikiem bieżącej wartości i znacznikiem percentyla z 10 lat (`percentile_10y`). Pasma podziałki w kolorach skali stanu wody, ale każdy próg ma też etykietę tekstową.

---

## 2. Kolory

Wszystkie pary policzone wzorem WCAG 2.x (luminancja względna). „Tło” = `--color-bg`, „pow.” = `--color-surface`.

### 2.1 Neutralne i marka (jasny — domyślny)

| Token | Hex | Użycie | Kontrast |
|---|---|---|---|
| `--color-bg` | `#F6F4EE` | tło strony („papier”) | — |
| `--color-surface` | `#FFFFFF` | pola formularza, sekcje raportu, panel Kolby | — |
| `--color-surface-sunken` | `#EAE6DB` | wnęki: tabela źródeł, pasek ładowania, kod działki | — |
| `--color-text` | `#1B1F1D` | tekst główny, nagłówki | 15.15 na tle, 16.66 na pow. |
| `--color-text-muted` | `#4D5450` | opisy, metadane, podpisy | 7.07 na tle, 7.78 na pow., 6.24 na wnęce |
| `--color-border` | `#D3CEC2` | linie dekoracyjne, separatory (nie granice kontrolek) | 1.43 (celowo, dekoracja) |
| `--color-border-strong` | `#767B74` | obramowanie pól formularza, checkboxów | 4.32 na pow., 3.93 na tle |
| `--color-primary` | `#0D5868` | „toń” — przyciski główne, linki, fokus | 7.31 na tle, 6.44 na wnęce |
| `--color-primary-hover` | `#09434F` | hover/pressed przycisku głównego | biały na nim 10.90 |
| `--color-on-primary` | `#FFFFFF` | tekst na `--color-primary` | 8.04 |
| `--color-primary-tint` | `#E2EDF0` | tło zaznaczonej opcji, aktywnego kroku | — |
| `--color-focus` | `#0D5868` | obrys fokusu (z odstępem 2 px od elementu) | 7.31 na tle |

### 2.2 Skala stanu wody / ryzyka suszy

Mapowanie z danych:
- `risk_level` z `Report.summary` (starsze raporty: `GET /api/report/{id}/summary`): `niska` → **dobry**, `średnia` → **podwyższone**, `wysoka` → **wysokie**, `null` → **brak oceny**.
- `soil_water.available_pct` (tylko wodowskaz, etykiety „Zapas dobry / niski / krytyczny”): ≥ 50% → good, 30–50% → watch, < 30% → high. To nie jest ocena ryzyka — ryzyko pokazujemy wyłącznie z `risk_level` (backend łączy zapas z KBW, SPI, CDI i satelitą); bez oceny z backendu → „Brak oceny” / stan ładowania / błąd z ponowieniem.

Oś barw: woda (niebieski) → piasek (ochra) → spieczona glina (rdza). Unikamy pary zielony/czerwony (deuteranopia); niebieski i rdzawy rozróżnia każdy typ daltonizmu. **Kolor nigdy sam** — zawsze z etykietą i ikoną kształtu (kropla / kropla z kreską / pęknięta ziemia / znak zapytania).

| Poziom | Etykieta UI | Tekst `--color-level-*-text` | Tło `--color-level-*-tint` | Wypełnienie `--color-level-*-fill` (paski, wodowskaz) |
|---|---|---|---|---|
| `good` | „Ryzyko niskie” / „Zapas dobry” | `#1D5A85` (7.36 pow., 6.19 tint) | `#E2EDF5` | `#2F78AD` (4.33 tło, 4.76 pow.; biały tekst 4.76) |
| `watch` | „Ryzyko podwyższone” | `#7A5200` (5.89 tint; `#875B00` 5.95 pow.) | `#F8ECCD` | `#A87612` (3.63 tło, 3.99 pow.; tekst ink 4.18) |
| `high` | „Ryzyko wysokie” | `#97301A` (6.09 tint; 6.93 pow.) | `#F8E1D9` | `#B8421F` (4.98 tło, 5.47 pow.; biały 5.47) |
| `unknown` | „Brak oceny” | `#4D5450` (6.22 tint) | `#E7E6E1` | `#80857F` (3.42 tło) + kreskowanie |

### 2.3 Semantyczne

| Znaczenie | Gdzie | Tokeny |
|---|---|---|
| sukces / źródło `ok` | status źródeł danych | `--color-success` `#22603A` (7.49 pow.), `--color-success-tint` `#E1EFE4` (6.31) |
| ostrzeżenie / źródło `częściowo`, ograniczenie `ostrzeżenie` | | = poziom `watch` |
| krytyczne / źródło `brak`, ograniczenie `krytyczne`, błąd formularza | | = poziom `high` |
| informacja / ograniczenie `info` | | `--color-info` = `--color-primary`, tło `--color-primary-tint` |

Status nawadniania (`IrrigationAdvice.status`): `zalecane` → high, `monitoruj` → watch, `niezalecane` → good, `nie dotyczy` → unknown (z powodem z pola `reason`).

### 2.4 Tryb ciemny

Uzasadnienie: telefon wieczorem w kabinie / przy zmroku; system i tak to proponuje. Tryb jasny pozostaje podstawowy (słońce, druk). Włączany przez `prefers-color-scheme: dark` lub `data-theme="dark"` na `<html>` (`data-theme="light"` wymusza jasny).

| Token | Hex | Kontrast |
|---|---|---|
| bg / surface / sunken | `#121714` / `#1B211E` / `#232A26` | — |
| text | `#ECEAE3` | 15.06 tło, 13.60 pow. |
| text-muted | `#A8AFA9` | 8.09 tło, 7.30 pow., 6.55 wnęka |
| border / border-strong | `#2F3732` / `#7F8780` | — / 4.43 pow. |
| primary / on-primary | `#7CC6D6` / `#0B1A1E` | 9.41 tło / 9.24 |
| primary-hover / primary-tint | `#A3DAE6` / `#15303A` | on-primary na hover > 9; tekst na tincie > 10 |
| level good / watch / high / unknown (tekst i fill) | `#8EC3EA` / `#E9B84F` / `#F29A7C` / `#A8AFA9` | 8.69 / 8.91 / 7.55 / 7.30 na pow. |
| tinty good / watch / high | `#16293A` / `#33280E` / `#3A1D15` | tekst na tincie ≥ 7.09 |
| success / tint | `#86C99A` / `#16301F` | 8.45 / 7.34 |

### 2.5 Druk

`@media print`: zawsze paleta jasna, tło białe, bez cieni; elementy z klasą `.no-print` (nawigacja, Kolba, przyciski) ukryte. Linki drukują URL źródła. Raport musi się mieścić w A4 pionowo (regulamin 3.3 pkt 6).

---

## 3. Typografia

**Atkinson Hyperlegible Next** (Google Fonts, OFL) — krój zaprojektowany przez Braille Institute dla czytelności przy słabym widzeniu: odróżnialne `I l 1`, `O 0`, otwarte kształty, pełne polskie znaki (latin-ext). Dobrze znosi odblaski na ekranie. Do identyfikatorów działek, liczb w tabelach i jednostek — **Atkinson Hyperlegible Mono** (ta sama rodzina, `141201_1.0001.6509` czytelne znak po znaku). Fallback: `system-ui`, `ui-monospace`. Ładowanie: link Google Fonts w `frontend/src/index.html` (`display=swap`, tylko wagi 400–700); przy wdrożeniu KOWR można self-hostować pliki (OFL pozwala).

Skala (mobile-first; od 48rem dwa najwyższe stopnie rosną):

| Token | Rozmiar | Line-height | Waga | Użycie |
|---|---|---|---|---|
| `--text-xs` | 0.875rem (14 px) | 1.4 | 400 | tylko metadane (data pobrania, licencja). Nie dla treści. |
| `--text-sm` | 1rem (16 px) | 1.5 | 400 | podpisy, pomoc pola, tabela źródeł |
| `--text-base` | 1.125rem (18 px) | 1.55 | 400 | tekst główny, pola, przyciski |
| `--text-lg` | 1.375rem (22 px) | 1.35 | 600 | nagłówki sekcji raportu (h3), tytuły rekomendacji |
| `--text-xl` | 1.75rem → 2rem | 1.2 | 700 | h2 — kroki 1–5 |
| `--text-2xl` | 2.25rem → 2.75rem | 1.1 | 700 | h1 ekranu, zdanie oceny |
| `--text-display` | 3rem → 4rem | 1 | 700 | liczba na wodowskazie (np. „38%”) |

Zasady: długość wiersza `--measure` 68ch; liczby `font-variant-numeric: tabular-nums`; jednostki odstępem twardym (`38&nbsp;mm`); nagłówki bez wersalików, bez rozstrzelenia. Kontrast typograficzny buduje rozmiar + waga 700 vs 400, nie kolor.

---

## 4. Odstępy, siatka, kształty

- **Skala odstępów** (baza 4 px): `--space-1` 4 · `--space-2` 8 · `--space-3` 12 · `--space-4` 16 · `--space-5` 24 · `--space-6` 32 · `--space-7` 48 · `--space-8` 64 · `--space-9` 96.
- **Siatka:** margines boczny `--gutter` 16 px (telefon) → 24 px (≥ 48rem) → 32 px (≥ 90rem). Treść max `--content-max` 72rem.
- **Punkty przełamania:** baza 390 px (telefon), `48rem` (768, tablet), `64rem` (1024, dwie kolumny raportu), `90rem` (1440, szeroki desktop — oś kroków + mapa przyklejona obok). W CSS: `@media (width >= 48rem)`. W klasach: `md:` (48rem), `lg:` (64rem), `xl:` (90rem).
- **Cel dotykowy:** `--tap-min` 48 px (rękawice, wibracje w kabinie) — powyżej minimum WCAG 2.2 (24 px).
- **Promienie:** `--radius-sm` 4 px (znaczniki, chipy), `--radius-md` 8 px (pola, przyciski, sekcje), `--radius-lg` 12 px (panel Kolby, okno dialogowe), `--radius-full` (tylko kropki statusu). Druk i papier mają ostre krawędzie — nie przekraczamy 12 px.
- **Cienie:** prawie ich nie ma. Struktura = linie `--color-border` i tło wnęki. `--shadow-overlay` tylko dla elementów nad treścią (przyklejony pasek akcji na telefonie, panel Kolby, dialog). Brak cieni na sekcjach raportu.
- **Ruch:** `--duration-fast` 120 ms (hover, press), `--duration-base` 200 ms (rozwinięcie), `--ease-out` `cubic-bezier(0.2, 0, 0, 1)`. Przy `prefers-reduced-motion: reduce` animacje wyłączone (ładowanie pokazuje tekst i licznik, bez fali).

---

## 5. Komponenty i stany

Każdy interaktywny element ma stany: domyślny, hover (tylko `@media (hover: hover)`), `:focus-visible`, active/pressed, disabled, loading (jeśli wywołuje żądanie), error (jeśli przyjmuje dane).

**Fokus (globalnie):** `outline: 3px solid var(--color-focus); outline-offset: 2px`. Nigdy `outline: none` bez zamiennika. Fokus nie może być zasłonięty przez przyklejony pasek (WCAG 2.4.11) — `scroll-padding` na `html`.

| Komponent | Specyfikacja |
|---|---|
| **Przycisk główny** | tło `--color-primary`, tekst `--color-on-primary`, wys. min. 48 px, `--radius-md`, waga 700. Hover: `--color-primary-hover`. Disabled: tło `--color-surface-sunken`, tekst `--color-text-muted`, kursor domyślny, `aria-disabled` gdy ma tłumaczyć powód. Loading: etykieta zmienia się na czynność („Analizuję…”), przycisk zostaje szeroki, `aria-busy="true"`. Maks. jeden na ekran. |
| **Przycisk drugorzędny** | tło przezroczyste, obrys 2 px `--color-primary`, tekst `--color-primary`. Hover: tło `--color-primary-tint`. |
| **Link** | `--color-primary`, podkreślenie zawsze (thickness 1px, offset 0.15em); hover: grubsze podkreślenie. |
| **Pole tekstowe** | tło `--color-surface`, obrys 2 px `--color-border-strong`, wys. 48 px, etykieta nad polem (zawsze widoczna, nie placeholder), pomoc pod polem w `--text-sm` muted. Error: obrys `--color-level-high-fill`, komunikat pod polem z ikoną i tekstem w `--color-level-high-text`, powiązany `aria-describedby`, `aria-invalid="true"`. |
| **Wybór uprawy** | lista radio jako kafle (telefon: 1 kolumna, ≥ 48rem: 2–3 kolumny) — rolnik widzi wszystkie 14 upraw z `/api/crops` bez otwierania selecta; pod nazwą okres krytyczny (`critical_period`, `critical_label`). Zaznaczona: tło `--color-primary-tint`, obrys 2 px `--color-primary`, znacznik ✓ jako SVG. |
| **Znacznik poziomu (badge)** | tło `--color-level-*-tint`, tekst `--color-level-*-text`, ikona kształtu + słowo. `--radius-sm`, `--text-sm` 600. |
| **Status źródła** | kropka 10 px (`--radius-full`) + słowo „aktualne / częściowe / brak”; kolory: success / watch / high. |
| **Sekcja raportu** | `--color-surface`, obrys 1 px `--color-border`, `--radius-md`, padding `--space-5` (telefon `--space-4`). Nagłówek: numer kroku w kwadracie 40 px (`--color-text` na `--color-surface-sunken`), tytuł h2. |
| **Rekomendacja** | tytuł `--text-lg`, uzasadnienie (`justification`), pod spodem „Na podstawie:” z linkami do dowodów `evidence_ids` (E01–E22) i ekoschematem (`eco_scheme`) jako znacznik. Priorytet (`priority` 1–3) jako słowo „Najpierw / Potem / Warto rozważyć”, nie gwiazdki. |
| **Ograniczenie (`Limitation`)** | pasek z lewą krawędzią 4 px w kolorze severity, ikona, tekst; `krytyczne` na górze sekcji, której dotyczy (`section`). |
| **Pewność (`Confidence`)** | przy każdej sekcji: „Pewność: średnia — {reason}”. Tekst, nie wykres. |

Ikony: SVG inline, kreska 2 px, 24 px, `currentColor`, `aria-hidden="true"` gdy obok jest tekst. Bez emoji.

---

## 6. Wzorce ekranów

### 6.1 Formularz analizy (ekran startowy)
- h1: „Sprawdź wodę na swojej działce”. Pod spodem jedno zdanie, co dostanie rolnik (ocena, przyczyny, co zrobić) i że trwa to ok. 20 s.
- Trzy kroki w jednej kolumnie (także na desktopie — formularz ma 36rem szerokości, obok na ≥ 64rem przykładowy fragment raportu lub mapa działki po jej znalezieniu):
  1. **Działka:** pole „Numer działki ewidencyjnej” (font mono, przykład w pomocy: `141201_1.0001.6509`, `inputmode="text"`, `autocomplete="off"`, `spellcheck="false"`). Alternatywa przyciskiem drugorzędnym: „Użyj mojej lokalizacji” (Geolocation → `GET /api/parcel?lat&lon`). Po znalezieniu: karta potwierdzenia (gmina, obręb, nr, powierzchnia ha, czy rolnicza). 404 z `candidates` → lista „Czy chodziło o…”. Działka nierolnicza (`is_agricultural=false`) → ostrzeżenie `watch`: „To nie jest grunt rolny — raport pokaże ocenę wody, ale bez zaleceń nawadniania.” Nie blokujemy.
  2. **Data analizy:** `<input type="date">` z `min` = dziś − 10 lat, `max` = dziś, domyślnie dziś. Pomoc: „Możesz sprawdzić dowolny dzień z ostatnich 10 lat. Dla daty z przeszłości używamy tylko danych do tego dnia.”
  3. **Uprawa:** kafle radio (patrz 5).
- Przycisk główny „Sprawdź działkę” — na telefonie przyklejony do dołu (`--shadow-overlay`), aktywny także gdy formularz niepełny; po kliknięciu walidacja i fokus na pierwszym błędzie + podsumowanie błędów nad formularzem.

### 6.2 Ładowanie analizy (15–25 s)
- Zastępuje formularz w tym samym miejscu; fokus na nagłówku „Analizuję działkę 141201_1.0001.6509”.
- Lista etapów jako podziałka wodowskazu, która „napełnia się” od dołu: Działka i granice (ULDK) → Pogoda z 10 lat → Gleba → Zdjęcia satelitarne → Teren i cieki → Ocena i zalecenia. Backend nie raportuje postępu, więc etapy przełączają się według typowych czasów — **bez procentów i bez fałszywego paska postępu**. Opis: „Zwykle trwa 15–25 sekund.” + licznik sekund.
- `aria-live="polite"` ogłasza tylko zmianę etapu (nie każdą sekundę). `role="status"`.
- Po 35 s: dopisek „Trwa dłużej niż zwykle — pobieramy brakujące lata danych satelitarnych.” Przycisk drugorzędny „Anuluj” zawsze dostępny.
- Reduced motion: bez animacji fali, tylko lista z aktualnym etapem pogrubionym.

### 6.3 Raport
Kolejność stała, odzwierciedla KOWR. Na telefonie jedna kolumna; ≥ 64rem: treść (2/3) + kolumna boczna (1/3, przyklejona) z mapą `/api/report/{id}/map.png`, metadanymi i akcjami; ≥ 90rem: dodatkowo oś kroków 1–5 po lewej jako spis treści (`aria-current` na bieżącym).

0. **Nagłówek raportu:** działka (mono), gmina, uprawa, data analizy, „Dane meteo do: {meteo_until}”. Akcje: „Pobierz PDF” (`/api/report/{id}.pdf`), „Drukuj”, „Nowa analiza”. `mock=true` → stały baner „Dane przykładowe — nie do decyzji”.
1. **Ocena stanu wody** — zdanie `headline` z `Report.summary` (`--text-2xl`), znacznik poziomu, wodowskaz (`available_pct`, `percentile_10y`), 3–4 kluczowe liczby z `findings` / `climate` (KBW 60 dni, opad 30 dni vs norma, dni bez opadu, dni stresu w sezonie). Kalendarz ryzyka (`risk_calendar`, dekady) jako pasek 36 komórek w skali poziomów, z tekstową listą „Najbardziej ryzykowne: maj–lipiec”. Brak `water` → stan „Brak oceny” z treścią z backendu i komunikatem, że bez oceny nie ma rekomendacji; kroki 2–5 widoczne jako wyszarzone nagłówki z tym samym wyjaśnieniem (nie ukryte).
2. **Przyczyny** — `causes` po `rank`, każda: etykieta, wkład w mm (jeśli jest) jako poziomy pasek wspólnej skali, `evidence` jako tekst.
3. **Retencja** — `recommendations` z `category="retencja"`, posortowane po `priority`. Lokalizacja (`location`) → odnośnik „Pokaż na mapie”.
4. **Agrotechnika** — `category="agrotechnika"`; dodatkowo `scenarios` jako „Co by dało…”: dni stresu przed/po (`stress_days_baseline` → `stress_days_scenario`).
5. **Nawadnianie** — karta `irrigation`: status jako znacznik, `reason`, a przy „zalecane”: pierwszy dzień, dawka netto/brutto mm, podział na N dawek, objętość m³, prognoza 7 dni (gdy `forecast_available`). `legal_note` zawsze widoczny. Działka nierolnicza lub `nie dotyczy` → sekcja zostaje, z powodem.
6. **Źródła danych i ograniczenia** — tabela `sources` (nazwa, okres, pobrano, status, licencja, link) i lista `limitations` pogrupowana po severity, plus `confidence` per sekcja. Na telefonie tabela zamienia się w listę definicji. Ta sekcja jest pełnoprawna, nie schowana w stopce — to kryterium oceny (25%).

### 6.4 Asystent Kolba
- Telefon: przycisk „Zapytaj Kolbę” w przyklejonym pasku pod raportem → panel od dołu (dialog, 85% wysokości). ≥ 64rem: panel w kolumnie bocznej pod mapą.
- Na start: gotowe pytania z `/api/assistant/questions` jako chipy (przyciski), pole tekstowe (max 500 znaków, licznik) i „Wyślij”.
- Odpowiedź: tekst + „Źródła: E07, E12” jako linki do rejestru dowodów; podpis trybu (`mode`), np. „Odpowiedź z gotowych pytań (bez modelu AI)”. Stała informacja: „Kolba odpowiada tylko na podstawie tego raportu. Nie liczy nowych wyników.”
- Stany: wysyłanie (pole zablokowane, „Kolba pisze…” w `aria-live`), błąd (komunikat + „Spróbuj ponownie”), tryb offline (tylko chipy, pole ukryte z wyjaśnieniem).
- Dialog: fokus w środku, Esc zamyka, fokus wraca na przycisk.

### 6.5 Stany puste i błędów
Wzór: ikona 32 px w kolorze poziomu, nagłówek mówiący co się stało, jedno zdanie dlaczego, jedna akcja. Ton: rzeczowy, po ludzku, bez „Ups!”.
- Działka nie znaleziona: „Nie znaleźliśmy działki 1412…” + kandydaci lub „Sprawdź numer w wypisie z ewidencji albo użyj lokalizacji”.
- Brak sieci / 5xx: „Nie udało się połączyć z serwerem analiz.” + „Spróbuj ponownie” (formularz zachowuje dane).
- Przekroczony czas: „Analiza trwa za długo.” + ponów; informacja, że kolejna próba będzie szybsza (cache).
- Źródło `brak`: w raporcie przy sekcji, nie modal.
- Raport nie istnieje (`/report/{id}` 404): „Ten raport nie jest już dostępny.” + „Nowa analiza”.

---

## 7. Responsywność i dostępność (checklista projektu)

- Mobile-first; testowane na 390 / 768 / 1440 px oraz 320 px i zoom 200% (bez przewijania w poziomie poza tabelą źródeł w kontenerze z `overflow-x: auto` i `tabindex="0"`).
- `lang="pl"`, unikalny `<title>` na widok („Raport — działka 141201_1.0001.6509 — Wodiva”), po zmianie widoku fokus na h1.
- Link „Przejdź do treści”, landmarki `header / main / footer`, jedna h1.
- Kolory nigdy jako jedyny nośnik informacji; wykresy mają tekstową alternatywę (lista lub tabela).
- Formularze: etykiety, błędy tekstem i `aria-describedby`, podsumowanie błędów.
- Dynamiczne treści (etap ładowania, odpowiedź Kolby) w `aria-live="polite"`.
- `prefers-reduced-motion`, `prefers-color-scheme`, `forced-colors` (obrysy zamiast teł).

---

## 8. Do / Don't

**Do**
- Zdanie oceny i poziom ryzyka zawsze pierwsze.
- Numeracja kroków 1–5 i ich kolejność we wszystkich widokach i w PDF.
- Każda liczba z jednostką, datą danych i źródłem w zasięgu jednego kliknięcia.
- „Brak danych” jako stan z powodem.
- Linie i tło wnęki do grupowania zamiast cieni.

**Don't**
- Gradienty (fioletowe, „wodne”, jakiekolwiek), tekst z gradientem, glassmorphism.
- Emoji jako ikony; ikony bez etykiety tekstowej w kluczowych miejscach.
- Zielony = dobrze / czerwony = źle jako jedyne rozróżnienie.
- Rzędy identycznych kart KPI z dużą liczbą i bez kontekstu.
- Procentowy pasek postępu, który nie odpowiada prawdziwemu postępowi.
- Ukrywanie sekcji nawadniania lub rekomendacji, gdy ich nie ma — zawsze pokazujemy dlaczego.
- Tekst mniejszy niż 14 px; szary tekst jaśniejszy niż `--color-text-muted`.
- Liczby wygenerowane przez Kolbę — w UI liczby pochodzą wyłącznie z pól raportu.

## 9. Tailwind v4 — mapowanie tokenów

Każdy token koloru `--color-X` daje klasy `bg-X`, `text-X`, `border-X` (np. `bg-surface`, `text-text-muted`, `bg-level-high-tint`, `fill-level-good-fill`). Pozostałe:

| Token | Klasa |
|---|---|
| `--font-sans` (= `--font-body`), `--font-mono` | `font-sans`, `font-mono` |
| `--text-xs` … `--text-display` | `text-xs` … `text-display` |
| `--leading-tight/snug/body` | `leading-tight/snug/body` |
| `--radius-sm/md/lg/full` | `rounded-sm/md/lg/full` |
| `--shadow-overlay` | `shadow-overlay` |
| `--container-content/form/measure` | `max-w-content/form/measure` |
| `--space-1…9` | baza `--spacing` = 0.25rem: `--space-4` = `p-4`, `--space-5` = `p-6`, `--space-6` = `p-8`, `--space-7` = `p-12`, `--space-8` = `p-16`, `--space-9` = `p-24` |
| `--tap-min` | `min-h-12 min-w-12` |

Tryb ciemny: kolory przełączają się same (`light-dark()`); wariant `dark:` jest podpięty pod ten sam przełącznik (`data-theme` albo ustawienie systemu). Nie używaj klas z dowolną wartością koloru (`bg-[#…]`) — nowy kolor najpierw do tabeli w §2.

