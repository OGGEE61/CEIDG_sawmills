import requests
import csv
import time
import random
import os

def get_free_proxies():
    try:
        res = requests.get("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt")
        proxies = res.text.strip().split("\n")
        return [p.strip() for p in proxies if p.strip()]
    except:
        return []

def main():
    print("Pobieram listę darmowych serwerów proxy do rotacji IP...")
    proxies_list = get_free_proxies()
    print(f"Znaleziono {len(proxies_list)} darmowych serwerów proxy.")
    
    target_pkds = ["16.10.Z", "16.11.Z", "16.12.Z"]
    per_page = 100
    output_file = "all_candidates.csv"
    
    file_exists = os.path.isfile(output_file)
    
    with open(output_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["krs", "name_discovery", "nip_discovery", "regon_discovery", "city_discovery", "status_discovery", "discovery_sources"])
        if not file_exists:
            writer.writeheader()
        
        current_proxy = None
        
        for pkd in target_pkds:
            print(f"\n--- Rozpoczynam pobieranie kandydatów dla PKD: {pkd} ---")
            page = 1
            
            while True:
                proxy_dict = {"http": f"http://{current_proxy}", "https": f"http://{current_proxy}"} if current_proxy else None
                ip_desc = current_proxy if current_proxy else "Własne IP"
                
                print(f"Pobieram stronę {page} dla {pkd} przez: {ip_desc}")
                
                try:
                    url = f"https://sprawdz-firme.pl/api/v1/search?pkd={pkd}&per_page={per_page}&page={page}"
                    res = requests.get(url, proxies=proxy_dict, timeout=10)
                    
                    if res.status_code == 200:
                        data = res.json()
                        items = data.get("results") or data.get("data") or []
                        if not items:
                            print(f"Brak więcej wyników dla {pkd} (pusta strona). Koniec tego kodu.")
                            break
                            
                        for item in items:
                            krs = item.get("krs")
                            if krs:
                                krs = "".join(filter(str.isdigit, str(krs))).zfill(10)
                                row = {
                                    "krs": krs,
                                    "name_discovery": item.get("name") or item.get("firma"),
                                    "status_discovery": item.get("status"),
                                    "discovery_sources": f"{pkd}:main"
                                }
                                writer.writerow(row)
                        f.flush()
                        page += 1
                        time.sleep(0.5 if not current_proxy else 0.1)
                    else:
                        print(f"Błąd HTTP {res.status_code}. Zmieniam proxy...")
                        if current_proxy and current_proxy in proxies_list:
                            proxies_list.remove(current_proxy)
                        current_proxy = random.choice(proxies_list) if proxies_list else None
                        
                except Exception as e:
                    print(f"Wyjątek połączenia (pewnie zły proxy). Zmieniam na inne...")
                    if current_proxy and current_proxy in proxies_list:
                        proxies_list.remove(current_proxy)
                    current_proxy = random.choice(proxies_list) if proxies_list else None

if __name__ == "__main__":
    main()
