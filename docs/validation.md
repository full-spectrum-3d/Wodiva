# Walidacja – osoba A (meteo, gleba, model wody)

Data uruchomienia: 2026-11-21. Przebiegi: 25, udane: 22.

Czas analizy: mediana 8.9 s, maks. 29.2 s, poniżej 30 s: 22/22.

Opad model vs IMGW (12 mies.): mediana różnicy 23%.

| region | date | crop | parcel_id | soil_cat | kbw_period | kbw_threshold | kbw_drought | available_pct | stress_days | irrigation | imgw_precip_diff_pct | seconds | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dolnośląskie | 2018-06-20 | pszenica_ozima | 022304_5.0032.1/112 | IV | -133.5 | -231.0 | False | 19.1 | 23 | zalecane | 38.1 | 15.8 |  |
| kujawsko-pomorskie | 2019-06-10 | kukurydza_ziarno | 040708_2.0004.20 | III | -104.0 | None | None | 57.2 | 0 | monitoruj | 16.6 | 1.6 |  |
| lubelskie | 2022-07-20 | rzepak_ozimy | 061704_2.0011.383/2 | III | -116.8 | None | None | 36.7 | 32 | niezalecane | 37.5 | 1.6 |  |
| lubuskie | 2024-05-25 | ziemniak | 080204_2.0003.319/1 | III | -108.0 | None | None | 94.7 | 22 | niezalecane | 7.6 | 9.0 |  |
| łódzkie | 2017-07-05 | burak_cukrowy |  |  |  |  |  |  |  |  |  | 59.9 | SourceError: meteo: brak danych meteorologicznych (ERA5 i Open-Meteo niedostępne) |
| małopolskie | 2018-06-20 | pszenica_ozima | 121401_2.0011.109/6 | IV | -164.7 | -231.0 | False | 19.0 | 24 | zalecane | 27.7 | 10.6 |  |
| mazowieckie | 2019-06-10 | kukurydza_ziarno | 143410_2.0002.326 | III | -67.2 | None | None | 60.8 | 0 | monitoruj | 51.7 | 9.7 |  |
| opolskie | 2022-07-20 | rzepak_ozimy | 160703_5.0011.945 | IV | -118.0 | None | None | 20.3 | 61 | nie dotyczy | 32.7 | 28.6 |  |
| podkarpackie | 2024-05-25 | ziemniak | 181004_2.0005.3254/1 | IV | -99.1 | None | None | 52.9 | 14 | zalecane | 51.5 | 8.5 |  |
| podlaskie | 2017-07-05 | burak_cukrowy | 200212_5.0023.154/2 | II | -90.5 | -237.0 | False | 48.4 | 10 | monitoruj | -15.0 | 9.3 |  |
| pomorskie | 2018-06-20 | pszenica_ozima | 221309_5.0012.5 | III | -185.8 | -204.0 | False | 5.3 | 32 | zalecane | 24.2 | 29.2 |  |
| śląskie | 2019-06-10 | kukurydza_ziarno | 241307_2.0003.184/1 | IV | -29.7 | None | None | 79.0 | 0 | niezalecane | 22.3 | 8.9 |  |
| świętokrzyskie | 2022-07-20 | rzepak_ozimy | 261208_5.0009.151 | III | -140.5 | None | None | 28.1 | 49 | niezalecane | 15.0 | 8.8 |  |
| warmińsko-mazurskie | 2024-05-25 | ziemniak |  |  |  |  |  |  |  |  |  | 2.3 | ParcelLookupError: Nie znaleziono działki w tym miejscu: brak wyników |
| wielkopolskie | 2017-07-05 | burak_cukrowy | 302109_5.0020.442/2 | III | -43.0 | -264.0 | False | 45.8 | 2 | monitoruj | 20.2 | 9.6 |  |
| zachodniopomorskie | 2018-06-20 | pszenica_ozima | 321409_2.0008.73 | III | -191.3 | -204.0 | False | 5.5 | 34 | zalecane | 19.9 | 8.8 |  |
| lubelskie-2 | 2019-06-10 | kukurydza_ziarno | 061401_1.0003.967/3 | III | -45.9 | None | None | 59.6 | 0 | nie dotyczy | 25.6 | 9.1 |  |
| wielkopolskie-2 | 2022-07-20 | rzepak_ozimy | 300701_2.0025.22 | III | -161.4 | None | None | 11.7 | 71 | niezalecane | 31.3 | 9.0 |  |
| mazowieckie-2 | 2024-05-25 | ziemniak | 140208_2.0021.20 | III | -116.8 | None | None | 27.6 | 26 | zalecane | 6.4 | 8.8 |  |
| podlaskie-2 | 2017-07-05 | burak_cukrowy |  |  |  |  |  |  |  |  |  | 51.4 | SourceError: meteo: brak danych meteorologicznych (ERA5 i Open-Meteo niedostępne) |
| dolnośląskie | 2026-11-21 | pszenica_ozima | 022304_5.0032.1/112 | IV | -55.9 | None | None | 100.0 | 0 | nie dotyczy | 10.2 | 28.0 |  |
| kujawsko-pomorskie | 2026-11-21 | kukurydza_ziarno | 040708_2.0004.20 | III | -12.2 | -232.0 | False | 74.6 | 0 | nie dotyczy | 15.7 | 3.0 |  |
| lubelskie | 2026-11-21 | rzepak_ozimy | 061704_2.0011.383/2 | III | -102.5 | -205.0 | False | 100.0 | 5 | nie dotyczy | 26.5 | 2.9 |  |
| lubuskie | 2026-11-21 | ziemniak | 080204_2.0003.319/1 | III | -64.5 | None | None | 99.9 | 0 | nie dotyczy | 32.9 | 2.1 |  |
| łódzkie | 2026-11-21 | burak_cukrowy | 100608_2.0012.18/13 | III | -68.8 | -182.0 | False | 72.1 | 0 | nie dotyczy | 13.6 | 2.5 |  |

Porównanie z IUNG Monitoring Suszy: wpisz ręcznie wynik IUNG (susza tak/nie) dla gminy, uprawy i okresu w kolumnie `iung` pliku CSV i uruchom ponownie z `--compare`.