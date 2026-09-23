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
