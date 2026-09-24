#!/usr/bin/env python3
"""
Build a Poland KRS database of entities whose registered activity contains
sawmilling / sawmill-related PKD codes.

Pipeline:
1. DISCOVERY: query a public company-search API by exact PKD code(s) to obtain
   candidate KRS numbers. This service is used only to discover candidate IDs.
2. VERIFICATION: fetch each candidate from the official Ministry of Justice
   Open API KRS and inspect the official current extract for PKD matches.
3. OUTPUT: write candidates.csv, tartaki.csv, errors.csv incrementally.

Target PKD:
- 16.10.Z (PKD 2007) - Produkcja wyrobów tartacznych
- 16.11.Z (PKD 2025) - Produkcja wyrobów tartacznych
- 16.12.Z (PKD 2025) - Obróbka i wykończanie wyrobów tartacznych

The script is deliberately conservative with request rates because the
official KRS Open API does not publish a rate limit/SLA.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DISCOVERY_URL = "https://sprawdz-firme.pl/api/v1/search"
KRS_API_URL = "https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{krs}"

TARGET_PKD = {
    "16.10.Z": "PKD 2007 - Produkcja wyrobów tartacznych",
    "16.11.Z": "PKD 2025 - Produkcja wyrobów tartacznych",
    "16.12.Z": "PKD 2025 - Obróbka i wykończanie wyrobów tartacznych",
}

DEFAULT_PER_PAGE = 100
DEFAULT_DELAY = 0.25
DEFAULT_TIMEOUT = 30


def normalize_krs(value: Any) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return None
    digits = digits[-10:]
    if len(digits) != 10:
        return None
    return digits.zfill(10)


def normalize_code(code: str) -> str:
    code = str(code).strip().upper()
    code = code.replace(" ", "")
    if re.fullmatch(r"\d{2}\.\d{2}\.\w", code):
        return code
    # Accept forms like 1610Z, 16.10Z, 1610.Z.
    m = re.fullmatch(r"(\d{2})\.?([0-9]{2})\.?([A-Z])", code)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    raise ValueError(f"Nieprawidłowy kod PKD: {code}")


def pkd_from_item(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    # KRS Open API exposes separate parts: kodDzial, kodKlasa, kodPodklasa.
    d = item.get("kodDzial")
    k = item.get("kodKlasa")
    p = item.get("kodPodklasa")
    if d is not None and k is not None and p is not None:
        return f"{str(d).strip()}.{str(k).strip().zfill(2)}.{str(p).strip().upper()}"

    # Some mirrors may return a ready-made code field.
    for key in ("kod", "code", "pkd"):
        if item.get(key):
            raw = str(item[key]).upper().replace(" ", "")
            m = re.search(r"\d{2}\.\d{2}\.\w", raw)
            if m:
                return m.group(0)
            m = re.search(r"\d{4}[A-Z]", raw)
            if m:
                return f"{m.group(0)[:2]}.{m.group(0)[2:4]}.{m.group(0)[4]}"
    return None


def parse_activity_section(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (main_pkd_items, other_pkd_items) from the activity section."""
    odpis = payload.get("odpis")
    if not isinstance(odpis, dict):
        return [], []

    dane = odpis.get("dane")
    if not isinstance(dane, dict):
        return [], []

    # Current KRS responses put activity in dzial3. Keep a fallback because
    # external mirrors / historic payload examples sometimes expose it under
    # another section.
    activity = None
    for section_name in ("dzial3", "dzial1"):
        section = dane.get(section_name)
        if isinstance(section, dict) and isinstance(section.get("przedmiotDzialalnosci"), dict):
            activity = section["przedmiotDzialalnosci"]
            break

    if not isinstance(activity, dict):
        return [], []

    def clean(items: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return out
        for item in items:
            code = pkd_from_item(item)
            if code:
                out.append({
                    "code": code,
                    "description": item.get("opis"),
                })
        return out

    return (
        clean(activity.get("przedmiotPrzewazajacejDzialalnosci")),
        clean(activity.get("przedmiotPozostalejDzialalnosci")),
    )


def find_dict_with_key(obj: Any, key: str) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        if key in obj:
            return obj
        for value in obj.values():
            found = find_dict_with_key(value, key)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_dict_with_key(item, key)
            if found:
                return found
    return None


def pick_first(payload: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        cur: Any = payload
        ok = True
        for part in path:
            if not isinstance(cur, dict) or part not in cur:
                ok = False
                break
            cur = cur[part]
        if ok and cur not in (None, "", []):
            return cur
    return None


def extract_company(payload: dict[str, Any], source_status: str | None = None) -> dict[str, Any]:
    odpis = payload.get("odpis", {}) if isinstance(payload, dict) else {}
    dane = odpis.get("dane", {}) if isinstance(odpis, dict) else {}
    dzial1 = dane.get("dzial1", {}) if isinstance(dane, dict) else {}
    dane_podmiotu = dzial1.get("danePodmiotu", {}) if isinstance(dzial1, dict) else {}
    ident = dane_podmiotu.get("identyfikatory", {}) if isinstance(dane_podmiotu, dict) else {}
    address_container = dzial1.get("siedzibaIAdres", {}) if isinstance(dzial1, dict) else {}
    address = address_container.get("adres", {}) if isinstance(address_container, dict) else {}

    main_pkd, other_pkd = parse_activity_section(payload)
    main_codes = [x["code"] for x in main_pkd]
    other_codes = [x["code"] for x in other_pkd]
    all_codes = list(dict.fromkeys(main_codes + other_codes))
    matches = [code for code in all_codes if code in TARGET_PKD]

    header = odpis.get("naglowekA", {}) if isinstance(odpis, dict) else {}
    if not isinstance(header, dict):
        header = {}

    company = {
        "krs": normalize_krs(ident.get("krs") or header.get("numerKRS")),
        "name": dane_podmiotu.get("nazwa"),
        "nip": ident.get("nip"),
        "regon": ident.get("regon"),
        "legal_form": dane_podmiotu.get("formaPrawna"),
        "register": header.get("rejestr"),
        "registration_date": header.get("dataRejestracjiWKRS"),
        "last_entry_date": header.get("dataOstatniegoWpisu"),
        "as_of": header.get("stanZDnia"),
        "status_from_discovery": source_status,
        "voivodeship": address.get("wojewodztwo"),
        "county": address.get("powiat"),
        "municipality": address.get("gmina"),
        "city": address.get("miejscowosc"),
        "street": address.get("ulica"),
        "building_no": address.get("nrDomu"),
        "unit_no": address.get("nrLokalu"),
        "postal_code": address.get("kodPocztowy"),
        "post_office": address.get("poczta"),
        "pkd_main": "; ".join(main_codes),
        "pkd_other": "; ".join(other_codes),
        "pkd_matches": "; ".join(matches),
        "pkd_match_types": "; ".join(
            "przeważające" if code in main_codes else "pozostałe"
            for code in matches
        ),
        "pkd_descriptions": "; ".join(
            f"{code}: {TARGET_PKD[code]}" for code in matches
        ),
        "share_capital": None,
        "share_capital_currency": None,
    }

    capital = find_dict_with_key(payload, "wysokoscKapitaluZakladowego")
    if capital:
        company["share_capital"] = capital.get("wysokoscKapitaluZakladowego")
        company["share_capital_currency"] = capital.get("walutaKapitaluZakladowego")

    return company


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "krs-tartaki-research/1.0"})
    return session


def request_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, Any] | None, str | None]:
    try:
        response = session.get(url, params=params, timeout=timeout, headers={"Accept": "application/json"})
    except requests.RequestException as exc:
        return 0, None, f"network_error: {exc}"

    if response.status_code in (204, 404):
        return response.status_code, None, None

    if response.status_code != 200:
        body = response.text[:300].replace("\n", " ")
        return response.status_code, None, f"http_{response.status_code}: {body}"

    try:
        data = response.json()
    except ValueError as exc:
        return response.status_code, None, f"invalid_json: {exc}"
    if not isinstance(data, dict):
        return response.status_code, None, "json_not_object"
    return response.status_code, data, None


def iter_discovery(
    session: requests.Session,
    *,
    pkd: str,
    additional: bool,
    status: str | None,
    per_page: int,
    timeout: int,
    delay: float,
) -> Iterable[dict[str, Any]]:
    page = 1
    while True:
        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }
        if additional:
            params["pkd_dodatkowe"] = pkd
        else:
            params["pkd"] = pkd
        if status:
            params["status"] = status

        code, payload, error = request_json(session, DISCOVERY_URL, params=params, timeout=timeout)
        if error:
            raise RuntimeError(f"Discovery failed for {pkd} page {page}: {error}")
        if code != 200 or payload is None:
            break

        items = payload.get("results") or payload.get("data") or []
        if isinstance(items, dict):
            items = items.get("results") or items.get("data") or []
        if not isinstance(items, list) or not items:
            break

        for item in items:
            if isinstance(item, dict):
                yield item

        meta = payload.get("meta", {})
        pages = meta.get("pages") or payload.get("pages")
        has_next = meta.get("has_next") if isinstance(meta, dict) else None
        if has_next is False:
            break
        if pages is not None:
            try:
                if page >= int(pages):
                    break
            except (TypeError, ValueError):
                pass
        elif len(items) < per_page:
            break

        page += 1
        if delay > 0:
            time.sleep(delay)


def discover_candidates(
    session: requests.Session,
    codes: list[str],
    out_csv: Path,
    *,
    include_inactive: bool,
    per_page: int,
    delay: float,
    timeout: int,
) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    status = None if include_inactive else "ACTIVE"

    for code in codes:
        for additional in (False, True):
            mode = "additional" if additional else "main"
            logging.info("Discovery: %s (%s)", code, mode)
            count_before = len(candidates)
            for item in iter_discovery(
                session,
                pkd=code,
                additional=additional,
                status=status,
                per_page=per_page,
                timeout=timeout,
                delay=delay,
            ):
                krs = normalize_krs(item.get("krs"))
                if not krs:
                    continue
                row = candidates.setdefault(
                    krs,
                    {
                        "krs": krs,
                        "name_discovery": item.get("name") or item.get("firma"),
                        "nip_discovery": item.get("nip"),
                        "regon_discovery": item.get("regon"),
                        "city_discovery": item.get("city") or item.get("miasto"),
                        "status_discovery": item.get("status"),
                        "discovery_sources": set(),
                    },
                )
                row["discovery_sources"].add(f"{code}:{mode}")
                for key, source_key in (
                    ("name_discovery", "name"),
                    ("nip_discovery", "nip"),
                    ("regon_discovery", "regon"),
                    ("city_discovery", "city"),
                    ("status_discovery", "status"),
                ):
                    if not row.get(key) and item.get(source_key):
                        row[key] = item.get(source_key)
                # Alternate field names used by some responses.
                for target, alt in (
                    ("name_discovery", "firma"),
                    ("city_discovery", "miasto"),
                ):
                    if not row.get(target) and item.get(alt):
                        row[target] = item[alt]
            logging.info("Discovery done: %s (%s): +%d candidates", code, mode, len(candidates) - count_before)

    fieldnames = [
        "krs", "name_discovery", "nip_discovery", "regon_discovery",
        "city_discovery", "status_discovery", "discovery_sources"
    ]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for krs in sorted(candidates):
            row = dict(candidates[krs])
            row["discovery_sources"] = "; ".join(sorted(row["discovery_sources"]))
            writer.writerow(row)

    return candidates


def load_candidates(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    out: dict[str, dict[str, Any]] = {}
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            krs = normalize_krs(row.get("krs"))
            if not krs:
                continue
            out[krs] = dict(row)
    return out


OUTPUT_FIELDS = [
    "krs", "name", "nip", "regon", "legal_form", "register",
    "registration_date", "last_entry_date", "as_of",
    "status_from_discovery", "voivodeship", "county", "municipality", "city",
    "street", "building_no", "unit_no", "postal_code", "post_office",
    "pkd_main", "pkd_other", "pkd_matches", "pkd_match_types", "pkd_descriptions",
    "share_capital", "share_capital_currency",
]

ERROR_FIELDS = ["krs", "status_code", "error", "name_discovery", "source_codes"]


def verify_candidates(
    session: requests.Session,
    candidates: dict[str, dict[str, Any]],
    out_csv: Path,
    errors_csv: Path,
    *,
    max_companies: int | None,
    delay: float,
    timeout: int,
    save_raw_dir: Path | None,
    resume: bool,
) -> tuple[int, int]:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    errors_csv.parent.mkdir(parents=True, exist_ok=True)
    if save_raw_dir:
        save_raw_dir.mkdir(parents=True, exist_ok=True)

    processed: set[str] = set()
    if resume and out_csv.exists():
        with out_csv.open("r", newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                krs = normalize_krs(row.get("krs"))
                if krs:
                    processed.add(krs)

    write_header = not out_csv.exists() or not resume
    err_header = not errors_csv.exists() or not resume

    results_count = 0
    error_count = 0

    with out_csv.open("a" if resume else "w", newline="", encoding="utf-8-sig") as result_f, \
         errors_csv.open("a" if resume else "w", newline="", encoding="utf-8-sig") as error_f:
        result_writer = csv.DictWriter(result_f, fieldnames=OUTPUT_FIELDS)
        error_writer = csv.DictWriter(error_f, fieldnames=ERROR_FIELDS)
        if write_header:
            result_writer.writeheader()
        if err_header:
            error_writer.writeheader()

        todo = [k for k in sorted(candidates) if k not in processed]
        if max_companies is not None:
            todo = todo[:max_companies]

        total = len(todo)
        for idx, krs in enumerate(todo, start=1):
            source = candidates[krs]
            url = KRS_API_URL.format(krs=krs)
            logging.info("Verify %d/%d: %s", idx, total, krs)
            status_code, payload, error = request_json(session, url, params={"rejestr": "P", "format": "json"}, timeout=timeout)

            if status_code == 200 and payload is not None:
                row = extract_company(payload, source_status=source.get("status_discovery"))
                if row.get("pkd_matches"):
                    result_writer.writerow(row)
                    result_f.flush()
                    results_count += 1
                    if save_raw_dir:
                        (save_raw_dir / f"{krs}.json").write_text(
                            json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
            else:
                # 404/204 are expected for stale candidates; keep them visible in errors.
                error_writer.writerow({
                    "krs": krs,
                    "status_code": status_code,
                    "error": error or ("not_found_or_deregistered" if status_code in (204, 404) else "unknown"),
                    "name_discovery": source.get("name_discovery"),
                    "source_codes": source.get("discovery_sources"),
                })
                error_f.flush()
                error_count += 1

            if delay > 0 and idx < total:
                time.sleep(delay)

    return results_count, error_count


def run_self_tests() -> None:
    sample = {
        "odpis": {
            "naglowekA": {
                "rejestr": "RejP",
                "numerKRS": "0001234567",
                "dataRejestracjiWKRS": "01.01.2020",
                "dataOstatniegoWpisu": "20.09.2026",
                "stanZDnia": "20.09.2026",
            },
            "dane": {
                "dzial1": {
                    "danePodmiotu": {
                        "nazwa": "TEST TARTAK SP. Z O.O.",
                        "identyfikatory": {"nip": "1234567890", "regon": "123456789"},
                        "formaPrawna": "SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ",
                    },
                    "siedzibaIAdres": {
                        "adres": {
                            "wojewodztwo": "WIELKOPOLSKIE",
                            "powiat": "POZNAŃSKI",
                            "gmina": "ROKIETNICA",
                            "miejscowosc": "ROKITNICA",
                            "ulica": "LEŚNA",
                            "nrDomu": "10",
                            "kodPocztowy": "62-090",
                        }
                    },
                },
                "dzial3": {
                    "przedmiotDzialalnosci": {
                        "przedmiotPrzewazajacejDzialalnosci": [
                            {"kodDzial": "16", "kodKlasa": "10", "kodPodklasa": "Z", "opis": "PRODUKCJA WYROBÓW TARTACZNYCH"}
                        ],
                        "przedmiotPozostalejDzialalnosci": [
                            {"kodDzial": "46", "kodKlasa": "73", "kodPodklasa": "Z", "opis": "SPRZEDAŻ HURTOWA"}
                        ],
                    }
                },
            }
        }
    }
    row = extract_company(sample, "ACTIVE")
    assert row["krs"] == "0001234567"
    assert row["pkd_matches"] == "16.10.Z"
    assert row["pkd_match_types"] == "przeważające"
    assert row["voivodeship"] == "WIELKOPOLSKIE"
    assert row["name"] == "TEST TARTAK SP. Z O.O."
    assert normalize_code("1611Z") == "16.11.Z"
    assert normalize_code("16.12.Z") == "16.12.Z"
    print("SELF-TEST OK")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Budowa bazy podmiotów KRS z PKD tartacznym.")
    sub = parser.add_subparsers(dest="command", required=True)

    t = sub.add_parser("test", help="Uruchom lokalne testy parsera bez internetu.")

    d = sub.add_parser("discover", help="Znajdź kandydatów po PKD i zapisz candidates.csv.")
    d.add_argument("--output", default="candidates.csv")
    d.add_argument("--codes", nargs="+", default=list(TARGET_PKD))
    d.add_argument("--include-inactive", action="store_true")
    d.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE)
    d.add_argument("--delay", type=float, default=1.0, help="Sekundy między stronami discovery.")
    d.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)

    v = sub.add_parser("verify", help="Zweryfikuj KRS z candidates.csv przez oficjalne API MS.")
    v.add_argument("--input", default="candidates.csv")
    v.add_argument("--output", default="tartaki.csv")
    v.add_argument("--errors", default="errors.csv")
    v.add_argument("--max-companies", type=int, default=None, help="Ile rekordów sprawdzić; świetne do testu.")
    v.add_argument("--delay", type=float, default=0.25, help="Sekundy między zapytaniami do KRS MS.")
    v.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    v.add_argument("--save-raw-dir", default=None, help="Opcjonalny katalog na surowe JSON z KRS.")
    v.add_argument("--resume", action="store_true", help="Pomiń KRS już obecne w tartaki.csv.")

    a = sub.add_parser("all", help="Discovery + verification w jednym poleceniu.")
    a.add_argument("--dir", default=".")
    a.add_argument("--codes", nargs="+", default=list(TARGET_PKD))
    a.add_argument("--include-inactive", action="store_true")
    a.add_argument("--max-companies", type=int, default=None)
    a.add_argument("--discovery-delay", type=float, default=1.0)
    a.add_argument("--krs-delay", type=float, default=0.25)
    a.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    a.add_argument("--save-raw", action="store_true")
    a.add_argument("--resume", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    if args.command == "test":
        run_self_tests()
        return 0

    session = build_session()

    if args.command == "discover":
        codes = [normalize_code(c) for c in args.codes]
        unknown = [c for c in codes if c not in TARGET_PKD]
        if unknown:
            raise SystemExit(f"Nieznane kody PKD: {unknown}. Dozwolone: {list(TARGET_PKD)}")
        candidates = discover_candidates(
            session,
            codes,
            Path(args.output),
            include_inactive=args.include_inactive,
            per_page=args.per_page,
            delay=args.delay,
            timeout=args.timeout,
        )
        logging.info("Gotowe: %d unikalnych kandydatów.", len(candidates))
        return 0

    if args.command == "verify":
        candidates = load_candidates(Path(args.input))
        raw_dir = Path(args.save_raw_dir) if args.save_raw_dir else None
        result_count, error_count = verify_candidates(
            session,
            candidates,
            Path(args.output),
            Path(args.errors),
            max_companies=args.max_companies,
            delay=args.delay,
            timeout=args.timeout,
            save_raw_dir=raw_dir,
            resume=args.resume,
        )
        logging.info("Weryfikacja zakończona: %d dopasowań, %d błędów/404/204.", result_count, error_count)
        return 0

    if args.command == "all":
        base = Path(args.dir)
        base.mkdir(parents=True, exist_ok=True)
        codes = [normalize_code(c) for c in args.codes]
        unknown = [c for c in codes if c not in TARGET_PKD]
        if unknown:
            raise SystemExit(f"Nieznane kody PKD: {unknown}. Dozwolone: {list(TARGET_PKD)}")

        candidates_path = base / "candidates.csv"
        tartaki_path = base / "tartaki.csv"
        errors_path = base / "errors.csv"
        raw_dir = base / "raw_krs" if args.save_raw else None

        candidates = discover_candidates(
            session,
            codes,
            candidates_path,
            include_inactive=args.include_inactive,
            per_page=DEFAULT_PER_PAGE,
            delay=args.discovery_delay,
            timeout=args.timeout,
        )
        logging.info("Discovery: %d kandydatów.", len(candidates))
        result_count, error_count = verify_candidates(
            session,
            candidates,
            tartaki_path,
            errors_path,
            max_companies=args.max_companies,
            delay=args.krs_delay,
            timeout=args.timeout,
            save_raw_dir=raw_dir,
            resume=args.resume,
        )
        logging.info("FINAL: %d dopasowań, %d błędów/404/204.", result_count, error_count)
        return 0

    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika. Przy kolejnym uruchomieniu użyj --resume.")
        raise SystemExit(130)
