import requests
import csv
import time
import random

def get_free_proxies():
    # Pobieranie listy darmowych proxy
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
    
    candidates = []
    page = 1
    max_records = 2000
    per_page = 100
    
    # Najpierw spróbujemy z naszego własnego IP (często wystarcza na 20-30 zapytań)
    use_proxy = False
    
    with open("candidates.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["krs", "name_discovery", "nip_discovery", "regon_discovery", "city_discovery", "status_discovery", "discovery_sources"])
        writer.writeheader()
        
        while len(candidates) < max_records:
            proxy_dict = None
            proxy_ip = None
            if use_proxy and proxies_list:
                proxy_ip = random.choice(proxies_list)
                proxy_dict = {"http": f"http://{proxy_ip}", "https": f"http://{proxy_ip}"}
            
            ip_desc = proxy_ip if proxy_ip else "Własne IP"
            print(f"Pobieram stronę {page} (znaleziono: {len(candidates)}/{max_records}) przez: {ip_desc}")
            
            try:
                url = f"https://sprawdz-firme.pl/api/v1/search?pkd=16.10.Z&per_page={per_page}&page={page}"
                res = requests.get(url, proxies=proxy_dict, timeout=10)
                
                if res.status_code == 200:
                    data = res.json()
                    items = data.get("results") or data.get("data") or []
                    if not items:
                        print("Brak więcej wyników z API (pusta strona).")
                        break
                        
                    for item in items:
                        krs = item.get("krs")
                        if krs:
                            krs = "".join(filter(str.isdigit, str(krs))).zfill(10)
                            row = {
                                "krs": krs,
                                "name_discovery": item.get("name") or item.get("firma"),
                                "status_discovery": item.get("status"),
                                "discovery_sources": "16.10.Z:main"
                            }
                            candidates.append(row)
                            writer.writerow(row)
                            if len(candidates) >= max_records:
                                break
                    f.flush()
                    page += 1
                else:
                    print(f"Błąd HTTP {res.status_code}. API zablokowało to IP. Zmieniam na inne...")
                    use_proxy = True
                    if proxy_ip and proxy_ip in proxies_list:
                        proxies_list.remove(proxy_ip)
            except Exception as e:
                print(f"Wyjątek połączenia (pewnie zły proxy). Zmieniam na inne...")
                use_proxy = True
                if proxy_ip and proxy_ip in proxies_list:
                    proxies_list.remove(proxy_ip)
            
            # Lekkie opóźnienie, żeby się zlitować nad API
            time.sleep(0.5 if not use_proxy else 0.1)

if __name__ == "__main__":
    main()
