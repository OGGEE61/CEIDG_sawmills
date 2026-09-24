import requests
import csv

url = "https://sprawdz-firme.pl/api/v1/search?pkd=16.10.Z&per_page=50"
response = requests.get(url)
data = response.json()

items = data.get("results") or data.get("data") or []
with open("candidates.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["krs", "name_discovery", "nip_discovery", "regon_discovery", "city_discovery", "status_discovery", "discovery_sources"])
    writer.writeheader()
    for item in items:
        krs = item.get("krs")
        if krs:
            krs = "".join(filter(str.isdigit, str(krs))).zfill(10)
            writer.writerow({
                "krs": krs,
                "name_discovery": item.get("name") or item.get("firma"),
                "status_discovery": item.get("status"),
                "discovery_sources": "16.10.Z:main"
            })
