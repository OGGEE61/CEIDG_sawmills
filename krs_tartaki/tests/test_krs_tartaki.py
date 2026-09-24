from krs_tartaki import extract_company, normalize_code


def test_pkd_parser_and_matching():
    payload = {
        "odpis": {
            "naglowekA": {"numerKRS": "1234567", "rejestr": "RejP"},
            "dane": {
                "dzial1": {
                    "danePodmiotu": {
                        "nazwa": "TARTAK TEST",
                        "identyfikatory": {"krs": "0001234567", "nip": "1111111111", "regon": "222222222"},
                        "formaPrawna": "SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ",
                    },
                    "siedzibaIAdres": {"adres": {"wojewodztwo": "WIELKOPOLSKIE"}},
                },
                "dzial3": {
                    "przedmiotDzialalnosci": {
                        "przedmiotPrzewazajacejDzialalnosci": [
                            {"kodDzial": "16", "kodKlasa": "11", "kodPodklasa": "Z", "opis": "PRODUKCJA WYROBÓW TARTACZNYCH"}
                        ],
                        "przedmiotPozostalejDzialalnosci": [
                            {"kodDzial": "46", "kodKlasa": "73", "kodPodklasa": "Z", "opis": "SPRZEDAŻ HURTOWA"}
                        ],
                    }
                },
            },
        }
    }
    row = extract_company(payload, "ACTIVE")
    assert row["krs"] == "0001234567"
    assert row["pkd_matches"] == "16.11.Z"
    assert row["pkd_match_types"] == "przeważające"
    assert row["status_from_discovery"] == "ACTIVE"
    assert normalize_code("1612Z") == "16.12.Z"
