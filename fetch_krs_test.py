import requests
import time
import json
import os

API_URL = "https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{krs}?rejestr=P&format=json"

def fetch_krs_test(start_id=1, limit=100):
    output_file = "krs_test_responses.jsonl"
    print(f"Rozpoczynam testowe pobieranie {limit} KRSów (od numeru {str(start_id).zfill(10)})...")
    
    found_count = 0
    with open(output_file, 'w', encoding='utf-8') as f:
        for i in range(start_id, start_id + limit):
            krs_str = str(i).zfill(10)
            url = API_URL.format(krs=krs_str)
            
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Spróbujmy wyciągnąć nazwę firmy, żeby ładnie to wypisać
                    nazwa = ""
                    try:
                        nazwa = data['odpis']['dane']['dzial1']['rubryka1']['danePodmiotu']['nazwa']
                    except KeyError:
                        pass
                        
                    print(f"[+] ZNALEZIONO KRS: {krs_str} | {nazwa}")
                    f.write(json.dumps({"krs": krs_str, "status": 200, "data": data}, ensure_ascii=False) + "\n")
                    found_count += 1
                elif response.status_code == 404:
                    print(f"[-] Brak KRS: {krs_str}", end="\r")
                    f.write(json.dumps({"krs": krs_str, "status": 404}, ensure_ascii=False) + "\n")
                else:
                    print(f"\n[!] Błąd HTTP {response.status_code} dla KRS: {krs_str} -> {response.text}")
                    f.write(json.dumps({"krs": krs_str, "status": response.status_code}, ensure_ascii=False) + "\n")
                
            except Exception as e:
                print(f"\n[!] Wyjątek przy KRS: {krs_str} -> {e}")
            
            # Opóźnienie 0.2s = max 5 zapytań/sek (grzecznie)
            time.sleep(0.2)
            
    print(f"\nKoniec. Znaleziono działających firm: {found_count}/{limit}")
    print(f"Pełne odpowiedzi JSON zapisano do pliku: {output_file}")

if __name__ == "__main__":
    fetch_krs_test(1, 100)
