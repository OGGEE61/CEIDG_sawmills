import requests
import pandas as pd
import time
import os

url_firmy = "https://dane.biznes.gov.pl/api/ceidg/v3/firmy"
url_firma = "https://dane.biznes.gov.pl/api/ceidg/v3/firma"
csv_filename = "ceidg_tartaki.csv"
state_filename = "state.txt"
headers = {
    "Authorization": "Bearer eyJraWQiOiJjZWlkZyIsImFsZyI6IkhTNTEyIn0.eyJnaXZlbl9uYW1lIjoiTWF4IiwicGVzZWwiOiI5OTAyMDIxMDY1MiIsImlhdCI6MTc5MDA2NTQ5NSwiZmFtaWx5X25hbWUiOiJTenBlcmxpxYRza2kiLCJjbGllbnRfaWQiOiJVU0VSLTk5MDIwMjEwNjUyLU1BWC1TWlBFUkxJxYNTS0kifQ.mswywrHBcFHUl_f1YHJPZaRyG0riNcaX4KNE862VsOx98jvg_CGlKGxreKZUiExipn9xvNmZeo5kxtp2KrdUZA"
}
limit = 25

# Wczytywanie stanu (od której strony zacząć)
page = 0
if os.path.exists(state_filename):
    with open(state_filename, "r") as f:
        try:
            page = int(f.read().strip())
            print(f"Wznawianie od strony {page}.")
        except ValueError:
            page = 0

print("Rozpoczynam pobieranie (weryfikacja przeważającego PKD)...")

while True:
    params = {
        "pkd": "1610Z", 
        "status": "AKTYWNY", 
        "limit": limit, 
        "page": page
    } 
    
    try:
        response = requests.get(url_firmy, headers=headers, params=params, timeout=15)
    except requests.exceptions.RequestException as e:
        print(f"Błąd połączenia (firmy): {e}. Oczekiwanie 180s...", flush=True)
        time.sleep(180)
        continue
    
    if response.status_code == 403:
        print(f"Błąd API 403 (Zablokowano - summary). Oczekiwanie 180s...", flush=True)
        time.sleep(180)
        continue
        
    if response.status_code != 200:
        print(f"Błąd API: {response.status_code} - {response.text}", flush=True)
        if response.status_code >= 500:
            time.sleep(60)
            continue
        break
        
    data = response.json()
    firmy_summary = data.get('firmy', [])
    
    if not firmy_summary:
        print("Brak więcej firm do pobrania. Koniec.")
        break
        
    valid_tartaki = []
    
    # Pobieranie szczegółów dla każdej firmy
    for i, f_summary in enumerate(firmy_summary):
        firm_id = f_summary.get('id')
        detail_url = f"{url_firma}/{firm_id}"
        
        while True:
            try:
                det_response = requests.get(detail_url, headers=headers, timeout=15)
            except requests.exceptions.RequestException as e:
                print(f"Błąd połączenia (firma {firm_id}): {e}. Oczekiwanie 180s...", flush=True)
                time.sleep(180)
                continue
                
            if det_response.status_code == 403:
                print(f"Błąd API 403 (Zablokowano - detale, wpis {i+1}/{len(firmy_summary)}). Oczekiwanie 180s...", flush=True)
                time.sleep(180)
                continue
                
            if det_response.status_code != 200:
                print(f"Błąd API Detali: {det_response.status_code} - {det_response.text}", flush=True)
                if det_response.status_code >= 500:
                    time.sleep(60)
                    continue
                break # Pomijamy firmę przy innych błędach
                
            det_data = det_response.json()
            firma_details_list = det_data.get('firma', [])
            if firma_details_list:
                firma_details = firma_details_list[0]
                pkd_glowny = firma_details.get('pkdGlowny', {})
                if pkd_glowny and pkd_glowny.get('kod') in ['1610Z', '16.10.Z']:
                    valid_tartaki.append(f_summary)
            
            # Lekkie opóźnienie
            time.sleep(0.5)
            break
            
    # Zapisz przefiltrowane tartaki
    if valid_tartaki:
        df_new = pd.json_normalize(valid_tartaki)
        write_header = not os.path.exists(csv_filename)
        df_new.to_csv(csv_filename, mode='a', index=False, header=write_header)
        
    print(f"Przetworzono stronę {page}. Znaleziono {len(valid_tartaki)} głównych tartaków na {len(firmy_summary)} firm.", flush=True)
    
    # Zapisz stan po udanej stronie
    page += 1
    with open(state_filename, "w") as f:
        f.write(str(page))