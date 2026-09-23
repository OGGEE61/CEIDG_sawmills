# CEIDG Sawmills Data Sourcing & Dashboard

This project provides tools to fetch, process, and visualize data about active sawmills (tartaki) from the Polish CEIDG (Centralna Ewidencja i Informacja o Działalności Gospodarczej) API v3. 

## Features

* **Data Sourcing (`fetch_data.py`)**: A Python script that queries the CEIDG API for businesses registered under specific PKD codes (1610Z, 1611Z). It features:
  * Batch processing of detailed company information.
  * Resumable state management (saves progress to avoid restarting from scratch).
  * Rate limit handling and automatic retries.
  * Output generation in both flattened CSV format and raw JSONL format.
* **Dashboard (`index.html`)**: A web interface for visualizing the fetched data.
* **Local Web Server (`serve.py`)**: A simple Python HTTP server to serve the dashboard and prevent caching issues during development.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(Requires `requests` and `pandas`)*
2. Set your CEIDG API token as an environment variable:
   ```bash
   export CEIDG_TOKEN="YOUR_TOKEN"
   ```
3. Run the data fetcher:
   ```bash
   python fetch_data.py
   ```
4. Start the local server to view the dashboard:
   ```bash
   python serve.py
   ```
   Then navigate to `http://localhost:8000/index.html`.

5. **Updating the database**: To scan for newly registered companies, use the `--update` flag:
   ```bash
   python fetch_data.py --update
   ```
   This will quickly scan all API pages and only fetch detailed data for new companies that aren't already in your database.

## Rozszerzenie bazy o Spółki z KRS (Opcjonalne)

Domyślnie skrypt `fetch_data.py` pobiera tylko jednoosobowe działalności z CEIDG. Aby dodać do bazy spółki (np. Sp. z o.o., Sp. k., S.A.), skorzystaj z darmowego pliku Otwartych Danych.

1. Pobierz plik CSV z wykazem podmiotów KRS ze strony [dane.gov.pl - Wykaz podmiotów zarejestrowanych w KRS](https://dane.gov.pl/pl/dataset/193,wykaz-podmiotow-zarejestrowanych-w-krs).
2. Zapisz rozpakowany plik na swoim komputerze (plik może zajmować kilka GB).
3. Uruchom skrypt przetwarzający, podając ścieżkę do pobranego pliku:
   ```bash
   python process_krs_dump.py /sciezka/do/pobranego_pliku.csv --sep ";"
   ```
4. Skrypt wyodrębni spółki tartaczne i zapisze je do pliku `tartaki_krs.csv`.
5. Odśwież Dashboard w przeglądarce. Aplikacja automatycznie załaduje i połączy dane z obu plików (CEIDG i KRS).

## Technical Details

**CEIDG API v3 Data Sourcing:**
* The script targets the `/firmy` endpoint to get a list of candidate companies using specific PKD codes (e.g., 1610Z = 2007 standard, 1611Z = 2025 standard).
* It then uses the `/firma` endpoint to fetch detailed data. This endpoint has a hidden limit of maximum 5 IDs per request, which the script handles by batching requests.
* Only companies whose *main* PKD code (pkdGlowny) matches the target list are saved.
* **Rate Limiting**: The API allows 50 requests / 3 minutes and 1000 requests / 60 minutes. The script waits ~3.7 seconds between requests to safely stay under limits. If a 403 or 429 is encountered, it sleeps for 185 seconds.
* **Resilience**:
  * State is continuously saved to `ceidg_state.json`. If interrupted (e.g. `Ctrl+C`), you can safely restart it to resume without duplicating work.
  * Server errors (5xx) are retried up to 5 times with exponential backoff.
  * Duplicate filtering runs on IDs present in both the state file and the CSV.
* **Data Flattening**: The nested JSON data from the API is flattened into dot-notation columns (e.g., `detail.adresDzialalnosci.wojewodztwo`) for easier visualization in the CSV. Long arrays are dumped as JSON strings.
