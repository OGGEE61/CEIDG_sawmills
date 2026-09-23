import os
import json
import time
import math
from pathlib import Path

import pandas as pd
import requests


# ============================================================
# CEIDG v3 - pobieranie firm z określonym PKD
# ============================================================
#
# Schemat:
#   /firmy?pkd=...&status=AKTYWNY
#       -> lista kandydatów + ID
#   /firma?ids=ID1&ids=ID2&...
#       -> szczegóły wielu firm w jednym request
#   -> sprawdzenie pkdGlowny
#   -> zapis do CSV
#
# Skrypt zapisuje stan na bieżąco, więc można go przerwać
# (Ctrl+C) i uruchomić ponownie.
#
# Wymagania:
#   pip install requests pandas
#
# Token najlepiej ustawić jako zmienną środowiskową:
#   Windows PowerShell:
#       $env:CEIDG_TOKEN="TWÓJ_TOKEN"
#
#   macOS/Linux:
#       export CEIDG_TOKEN="TWÓJ_TOKEN"
#
# albo wpisz token bezpośrednio w TOKEN poniżej.
# ============================================================


# -------------------------
# KONFIGURACJA
# -------------------------

TOKEN = os.getenv("CEIDG_TOKEN", "eyJraWQiOiJjZWlkZyIsImFsZyI6IkhTNTEyIn0.eyJnaXZlbl9uYW1lIjoiTWF4IiwicGVzZWwiOiI5OTAyMDIxMDY1MiIsImlhdCI6MTc5MDA2NTQ5NSwiZmFtaWx5X25hbWUiOiJTenBlcmxpxYRza2kiLCJjbGllbnRfaWQiOiJVU0VSLTk5MDIwMjEwNjUyLU1BWC1TWlBFUkxJxYNTS0kifQ.mswywrHBcFHUl_f1YHJPZaRyG0riNcaX4KNE862VsOx98jvg_CGlKGxreKZUiExipn9xvNmZeo5kxtp2KrdUZA")

BASE_URL = "https://dane.biznes.gov.pl/api/ceidg/v3"
FIRMY_URL = f"{BASE_URL}/firmy"
FIRMA_URL = f"{BASE_URL}/firma"

# PKD używane do wyszukania kandydatów.
# 1610Z = PKD 2007: Produkcja wyrobów tartacznych
# 1611Z = PKD 2025: Produkcja wyrobów tartacznych
#
# Jeżeli chcesz wyłącznie stare PKD 1610Z, ustaw:
# SEARCH_PKD_CODES = ["1610Z"]
SEARCH_PKD_CODES = ["1610Z", "1611Z"]

# Tylko firma, której PKD główne jest w tej liście,
# zostanie zapisana do wyniku.
MAIN_PKD_CODES = {
    "1610Z",
    "16.10.Z",
    "1611Z",
    "16.11.Z",
}

STATUS = "AKTYWNY"

# Dokumentacja API podaje limit 50 żądań / 3 minuty
# i 1000 żądań / 60 minut. 3.7 s między żądaniami
# daje bezpieczny margines względem 3.6 s.
REQUEST_INTERVAL = 3.7

# Po 403/429 odczekujemy ponad 180 s.
RATE_LIMIT_SLEEP = 185

# Maksymalna liczba firm w jednym zapytaniu szczegółowym.
BATCH_SIZE = 25

# Jak długo ponawiać błędy serwera 5xx.
MAX_RETRIES_5XX = 5

OUTPUT_CSV = "tartaki_ceidg.csv"
STATE_FILE = "ceidg_state.json"

# Ustaw True, żeby oprócz CSV zapisywać pełny JSON firmy.
SAVE_RAW_JSON = True
RAW_JSON_FILE = "tartaki_ceidg_raw.jsonl"


# -------------------------
# POMOCNICZE
# -------------------------

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
})

last_request_time = 0.0


def ensure_token():
    if not TOKEN or TOKEN == "WSTAW_TUTAJ_TOKEN":
        raise RuntimeError(
            "Brak tokena CEIDG. Ustaw zmienną CEIDG_TOKEN "
            "albo wpisz token w zmiennej TOKEN."
        )


def api_get(url, params=None, timeout=30):
    """
    GET z kontrolą częstotliwości i obsługą typowych błędów.
    """
    global last_request_time

    retries_5xx = 0

    while True:
        elapsed = time.monotonic() - last_request_time
        if last_request_time > 0 and elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)

        try:
            response = session.get(
                url,
                params=params,
                timeout=timeout,
            )
            last_request_time = time.monotonic()

        except requests.RequestException as exc:
            print(
                f"[NETWORK] {exc} | ponawiam za 30 s...",
                flush=True,
            )
            time.sleep(30)
            continue

        # Rate limit - w tym API może pojawić się 403.
        if response.status_code in (403, 429):
            print(
                f"[RATE LIMIT] HTTP {response.status_code}. "
                f"Czekam {RATE_LIMIT_SLEEP} s...",
                flush=True,
            )
            time.sleep(RATE_LIMIT_SLEEP)
            continue

        # Błędy serwera.
        if response.status_code >= 500:
            retries_5xx += 1
            if retries_5xx <= MAX_RETRIES_5XX:
                wait = min(60, 10 * retries_5xx)
                print(
                    f"[SERVER] HTTP {response.status_code}. "
                    f"Próba {retries_5xx}/{MAX_RETRIES_5XX} "
                    f"za {wait} s...",
                    flush=True,
                )
                time.sleep(wait)
                continue

        if response.status_code != 200:
            raise RuntimeError(
                f"HTTP {response.status_code} dla {url}\n"
                f"Parametry: {params}\n"
                f"Odpowiedź: {response.text[:2000]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"API zwróciło niepoprawny JSON dla {url}: "
                f"{response.text[:1000]}"
            ) from exc


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "completed_pages": {},
            "processed_ids": [],
            "detail_id_param": "ids",
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        state.setdefault("completed_pages", {})
        state.setdefault("processed_ids", [])
        state.setdefault("detail_id_param", "ids")
        return state

    except (json.JSONDecodeError, OSError):
        print(
            "[STATE] Nie udało się odczytać stanu. "
            "Zaczynam od początku.",
            flush=True,
        )
        return {
            "completed_pages": {},
            "processed_ids": [],
            "detail_id_param": "ids",
        }


def save_state(state):
    temp_file = STATE_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    os.replace(temp_file, STATE_FILE)


def jsonable(value):
    """
    Zamienia listy/dict na JSON string, żeby CSV był czytelny.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def flatten_json(obj, prefix=""):
    """
    Spłaszcza zagnieżdżony JSON:
        {"pkdGlowny": {"kod": "1610Z"}}
    ->
        {"pkdGlowny.kod": "1610Z"}
    """
    result = {}

    if isinstance(obj, dict):
        for key, value in obj.items():
            new_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                result.update(flatten_json(value, new_key))

            elif isinstance(value, list):
                # Długie tablice zapisujemy jako JSON.
                result[new_key] = json.dumps(
                    value,
                    ensure_ascii=False,
                )

            else:
                result[new_key] = value

    else:
        result[prefix] = obj

    return result


def first_value(data, possible_keys):
    """
    Zwraca pierwszą znalezioną niepustą wartość.
    Obsługuje również klucze zagnieżdżone, np. pkdGlowny.kod.
    """
    for key in possible_keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def get_detail_pkd_code(detail):
    """
    Odczytuje kod PKD głównego z odpowiedzi szczegółowej.
    """
    pkd = detail.get("pkdGlowny")

    if isinstance(pkd, dict):
        return str(pkd.get("kod", "")).strip().upper()

    # Awaryjnie, gdy API zwróci już spłaszczone pole.
    flat_code = detail.get("pkdGlowny.kod")
    if flat_code:
        return str(flat_code).strip().upper()

    return ""


def build_output_record(summary, detail):
    """
    Łączy dane z /firmy oraz /firma do jednego rekordu.
    Oprócz wybranych kolumn zachowuje cały zagnieżdżony JSON
    w postaci spłaszczonej.
    """

    summary_flat = flatten_json(summary, "summary")
    detail_flat = flatten_json(detail, "detail")

    merged = {}
    merged.update(summary_flat)
    merged.update(detail_flat)

    pkd_code = get_detail_pkd_code(detail)

    # Najważniejsze standardowe pola - jeśli istnieją.
    merged["CEIDG_ID"] = detail.get("id") or summary.get("id") or ""
    merged["PKD_GLOWNE_KOD"] = pkd_code

    pkd_obj = detail.get("pkdGlowny")
    if isinstance(pkd_obj, dict):
        merged["PKD_GLOWNE_NAZWA"] = pkd_obj.get("nazwa", "")
    else:
        merged["PKD_GLOWNE_NAZWA"] = ""

    # Typowe dane identyfikacyjne.
    merged["NIP"] = first_value(
        detail,
        ["nip", "NIP"],
    )
    merged["REGON"] = first_value(
        detail,
        ["regon", "REGON"],
    )
    merged["NAZWA"] = first_value(
        detail,
        ["nazwa", "nazwaFirmy", "firma"],
    )
    merged["STATUS"] = first_value(
        detail,
        ["status"],
    )

    # Typowe dane kontaktowe.
    merged["EMAIL"] = first_value(
        detail,
        ["email", "adresEmail", "emailFirmowy"],
    )
    merged["TELEFON"] = first_value(
        detail,
        ["telefon", "telefonKontaktowy", "numerTelefonu"],
    )
    merged["WWW"] = first_value(
        detail,
        ["www", "stronaWWW", "adresWWW", "website"],
    )

    return merged


def get_companies_page(pkd_code, page):
    """
    Pobiera jedną stronę /firmy.
    """
    params = {
        "pkd": pkd_code,
        "status": STATUS,
        "limit": BATCH_SIZE,
        "page": page,
    }

    return api_get(FIRMY_URL, params=params)


def get_company_details(ids, state):
    """
    Pobiera szczegóły wielu firm, wysyłając maksymalnie 5 ID w jednym zapytaniu.
    (API CEIDG ma ukryty limit 5 ID per request na endpoint /firma).
    """
    results = []
    
    # Dzielimy IDs na paczki po maksymalnie 5 sztuk
    for i in range(0, len(ids), 5):
        chunk = ids[i:i+5]
        params = [("ids", firm_id) for firm_id in chunk]
        try:
            res = api_get(FIRMA_URL, params=params)
            if "firma" in res:
                if isinstance(res["firma"], list):
                    results.extend(res["firma"])
                else:
                    results.append(res["firma"])
            else:
                results.append(res)
        except Exception as e:
            print(f"[WARN] Error fetching chunk {chunk}: {e}", flush=True)
            pass
            
    return {"firma": results}


def normalize_firma_response(data):
    """
    API zwykle zwraca:
        {"firma": [...]}

    Zabezpieczenie na wypadek innej struktury.
    """
    firmy = data.get("firma", [])

    if isinstance(firmy, dict):
        firmy = [firmy]

    if not isinstance(firmy, list):
        return []

    return firmy


def append_records_to_csv(records):
    """
    Dopisuje rekordy do CSV.
    utf-8-sig + ; jest wygodne dla Excela w Polsce.
    """

    if not records:
        return

    new_df = pd.DataFrame(records)

    # Stabilne, czytelne sortowanie kolumn:
    preferred = [
        "CEIDG_ID",
        "NAZWA",
        "NIP",
        "REGON",
        "STATUS",
        "PKD_GLOWNE_KOD",
        "PKD_GLOWNE_NAZWA",
        "EMAIL",
        "TELEFON",
        "WWW",
    ]

    with open("tartaki_ceidg.jsonl", "a", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Regenerate CSV perfectly aligned
    combined_df = pd.read_json("tartaki_ceidg.jsonl", lines=True, dtype=str)

    remaining = [
        c for c in combined_df.columns
        if c not in preferred
    ]

    combined_df = combined_df[preferred + remaining]

    combined_df.to_csv(
        OUTPUT_CSV,
        index=False,
        sep=";",
        encoding="utf-8-sig",
    )


def append_raw_json(records):
    if not SAVE_RAW_JSON or not records:
        return

    with open(
        RAW_JSON_FILE,
        "a",
        encoding="utf-8",
    ) as f:
        for record in records:
            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )


def load_processed_ids_from_csv():
    """
    Dodatkowe zabezpieczenie przed duplikatami po przerwaniu
    programu i ponownym uruchomieniu.
    """
    if not os.path.exists(OUTPUT_CSV):
        return set()

    try:
        df = pd.read_csv(
            OUTPUT_CSV,
            sep=";",
            encoding="utf-8-sig",
            usecols=["CEIDG_ID"],
            dtype=str,
        )
        return set(df["CEIDG_ID"].dropna().astype(str))
    except Exception:
        return set()


# -------------------------
# GŁÓWNY PROGRAM
# -------------------------

def main():
    ensure_token()

    print("=" * 70)
    print("CEIDG v3 - wyszukiwanie aktywnych tartaków")
    print("=" * 70)
    print(f"PKD wyszukiwane: {', '.join(SEARCH_PKD_CODES)}")
    print(f"PKD główne akceptowane: {', '.join(sorted(MAIN_PKD_CODES))}")
    print(f"Batch szczegółów: {BATCH_SIZE} firm")
    print(f"Odstęp między requestami: {REQUEST_INTERVAL} s")
    print(f"CSV: {OUTPUT_CSV}")
    print("=" * 70)

    state = load_state()

    # IDs już zapisane do CSV + IDs zapisane w state.
    processed_ids = set(
        str(x)
        for x in state.get("processed_ids", [])
    )

    processed_ids.update(
        load_processed_ids_from_csv()
    )

    total_saved = 0

    try:
        for pkd_code in SEARCH_PKD_CODES:

            page_key = str(pkd_code)
            page = int(
                state["completed_pages"].get(
                    page_key,
                    0,
                )
            )

            print()
            print("-" * 70)
            print(f"START PKD: {pkd_code}")
            print(f"Start od strony: {page}")
            print("-" * 70)

            while True:

                print(
                    f"[{pkd_code}] Pobieram stronę {page}...",
                    flush=True,
                )

                data = get_companies_page(
                    pkd_code,
                    page,
                )

                summaries = data.get("firmy", [])

                if not summaries:
                    print(
                        f"[{pkd_code}] Brak kolejnych firm. "
                        f"PKD zakończone.",
                        flush=True,
                    )
                    break

                print(
                    f"[{pkd_code}] Kandydatów na stronie: "
                    f"{len(summaries)}",
                    flush=True,
                )

                # Usuwamy ID już wcześniej przetworzone.
                candidate_summaries = []
                batch_ids = []

                for summary in summaries:
                    firm_id = summary.get("id")

                    if not firm_id:
                        continue

                    firm_id = str(firm_id)

                    if firm_id in processed_ids:
                        continue

                    candidate_summaries.append(summary)
                    batch_ids.append(firm_id)

                if not batch_ids:
                    print(
                        f"[{pkd_code}] Wszystkie firmy z tej strony "
                        f"były już przetworzone.",
                        flush=True,
                    )

                    page += 1
                    state["completed_pages"][page_key] = page
                    save_state(state)
                    continue

                print(
                    f"[{pkd_code}] Pobieram szczegóły dla "
                    f"{len(batch_ids)} firm w 1 request...",
                    flush=True,
                )

                detail_data = get_company_details(
                    batch_ids,
                    state,
                )

                details = normalize_firma_response(
                    detail_data
                )

                # Mapowanie szczegółów po ID.
                details_by_id = {}

                for detail in details:
                    detail_id = detail.get("id")

                    if detail_id:
                        details_by_id[str(detail_id)] = detail

                # Jeżeli API nie zwróciło któregoś ID, próbujemy
                # ponownie tylko dla brakujących. Dzięki temu nie
                # przesuniemy strony i nie zgubimy żadnej firmy.
                missing_ids = [
                    firm_id
                    for firm_id in batch_ids
                    if firm_id not in details_by_id
                ]

                if missing_ids:
                    print(
                        f"[WARN] API nie zwróciło szczegółów dla "
                        f"{len(missing_ids)} ID. Ponawiam batch brakujących...",
                        flush=True,
                    )

                    retry_data = get_company_details(
                        missing_ids,
                        state,
                    )

                    retry_details = normalize_firma_response(
                        retry_data
                    )

                    for detail in retry_details:
                        detail_id = detail.get("id")
                        if detail_id:
                            details_by_id[str(detail_id)] = detail

                    missing_ids = [
                        firm_id
                        for firm_id in batch_ids
                        if firm_id not in details_by_id
                    ]

                # Jeżeli po drugim żądaniu nadal brakuje danych,
                # zatrzymujemy program. Strona NIE zostanie oznaczona
                # jako ukończona, więc po ponownym uruchomieniu zostanie
                # pobrana ponownie.
                if missing_ids:
                    raise RuntimeError(
                        "API nie zwróciło szczegółów dla następujących ID "
                        "po ponowieniu: "
                        + ", ".join(missing_ids)
                    )

                accepted_records = []
                raw_records = []

                accepted_count = 0
                rejected_count = 0

                for summary in candidate_summaries:

                    firm_id = str(summary["id"])
                    detail = details_by_id[firm_id]

                    main_pkd = get_detail_pkd_code(
                        detail
                    )

                    # Weryfikujemy PKD główne.
                    if main_pkd in MAIN_PKD_CODES:

                        record = build_output_record(
                            summary,
                            detail,
                        )

                        accepted_records.append(record)

                        raw_records.append({
                            "summary": summary,
                            "detail": detail,
                        })

                        accepted_count += 1

                    else:
                        rejected_count += 1

                    # Firmę uznajemy za przetworzoną dopiero po
                    # otrzymaniu pełnej odpowiedzi szczegółowej.
                    processed_ids.add(firm_id)

                # Zapis wyników.
                append_records_to_csv(
                    accepted_records
                )

                append_raw_json(
                    raw_records
                )

                # Aktualizujemy state.
                state["processed_ids"] = list(
                    processed_ids
                )

                # Dopiero po udanym batchu przesuwamy stronę.
                page += 1
                state["completed_pages"][page_key] = page

                save_state(state)

                total_saved += accepted_count

                print(
                    f"[{pkd_code}] Strona zakończona | "
                    f"PKD główne pasuje: {accepted_count} | "
                    f"Odrzucone: {rejected_count} | "
                    f"Łącznie zapisanych w tej sesji: {total_saved}",
                    flush=True,
                )

                # Jeżeli API zwróci mniej niż limit, zwykle oznacza
                # to ostatnią stronę.
                if len(summaries) < BATCH_SIZE:
                    print(
                        f"[{pkd_code}] Otrzymano mniej niż "
                        f"{BATCH_SIZE} rekordów - prawdopodobnie "
                        f"ostatnia strona.",
                        flush=True,
                    )
                    break

    except KeyboardInterrupt:
        print()
        print(
            "Przerwano przez użytkownika (Ctrl+C). "
            "Stan został zapisany po ostatnim ukończonym batchu.",
            flush=True,
        )

    print()
    print("=" * 70)
    print("KONIEC")
    print(f"Wynik CSV: {OUTPUT_CSV}")

    if SAVE_RAW_JSON:
        print(f"Pełny JSON: {RAW_JSON_FILE}")

    print(f"State: {STATE_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    main()
