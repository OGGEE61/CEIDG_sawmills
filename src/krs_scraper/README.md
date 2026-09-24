# KRS Tartaki — baza podmiotów z PKD tartacznym

Ten projekt buduje listę polskich podmiotów z KRS, które w aktualnym odpisie KRS mają jeden z kodów:

- `16.10.Z` — PKD 2007, Produkcja wyrobów tartacznych
- `16.11.Z` — PKD 2025, Produkcja wyrobów tartacznych
- `16.12.Z` — PKD 2025, Obróbka i wykończanie wyrobów tartacznych

## Architektura

**Etap 1 — discovery**

Skrypt pyta publiczną wyszukiwarkę firm tylko po PKD, aby dostać numery KRS kandydatów. Kandydaci są zapisywani do `candidates.csv`.

**Etap 2 — verification**

Każdy kandydat jest odpytywany przez oficjalne Open API KRS Ministerstwa Sprawiedliwości:

`https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{KRS}?rejestr=P&format=json`

Dopiero ten etap decyduje, czy firma trafia do `tartaki.csv`.

## 1. Instalacja

Windows / macOS / Linux:

```bash
python -m pip install -r requirements.txt
```

## 2. Test bez internetu

```bash
python krs_tartaki.py test
```

Oczekiwany wynik:

```text
SELF-TEST OK
```

## 3. Discovery — najpierw tylko lista KRS

```bash
python krs_tartaki.py discover --output candidates.csv
```

Powstanie:

```text
candidates.csv
```

Sprawdź tę listę przed masową weryfikacją.

## 4. Test na 20 firmach

```bash
python krs_tartaki.py verify --input candidates.csv --output tartaki_test.csv --errors errors_test.csv --max-companies 20
```

To odpytuje oficjalny KRS tylko dla pierwszych 20 kandydatów.

## 5. Pełna weryfikacja

```bash
python krs_tartaki.py verify --input candidates.csv --output tartaki.csv --errors errors.csv --delay 0.25 --resume
```

`--resume` pozwala przerwać program i uruchomić go ponownie bez ponownego przetwarzania rekordów już zapisanych w `tartaki.csv`.

## 6. Surowe JSON-y KRS

Do audytu można zapisywać każdy pobrany odpis:

```bash
python krs_tartaki.py verify --input candidates.csv --output tartaki.csv --errors errors.csv --save-raw-dir raw_krs --resume
```

## Pliki wynikowe

`candidates.csv` — numery KRS znalezione na etapie discovery.

`tartaki.csv` — tylko podmioty, które zostały potwierdzone w aktualnym odpisie KRS jako posiadające docelowy kod PKD.

`errors.csv` — numery, dla których KRS zwrócił 404/204 albo wystąpił błąd techniczny.

`raw_krs/` — opcjonalne, surowe JSON-y.

## Ważne

Dla `16.10.Z` zachowujemy starą klasyfikację PKD 2007. Dla `16.11.Z` i `16.12.Z` zachowujemy PKD 2025. Rekord w `tartaki.csv` zawiera osobno `pkd_main`, `pkd_other`, `pkd_matches` i `pkd_match_types`, więc łatwo później odseparować tartaki, dla których ten kod jest działalnością przeważającą, od firm z kodem pobocznym.
