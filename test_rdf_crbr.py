import requests
import json
import urllib3
import pandas as pd
urllib3.disable_warnings()

print("Looking for a test KRS and NIP from tartaki_full.csv...")
df = pd.read_csv('data/processed/tartaki_full.csv', dtype=str)
test_row = df[(df['krs'].notna()) & (df['nip'].notna())].iloc[0]
krs = test_row['krs'].zfill(10)
nip = test_row['nip']
name = test_row['name']
print(f"Testing with: {name}, KRS: {krs}, NIP: {nip}")

# Test CRBR
print("\n--- Testing CRBR API ---")
try:
    # Proper CRBR endpoint? Let's check a few variations.
    res = requests.get(f"https://crbr.podatki.gov.pl/api/app/rest/search/findByNip?nip={nip}", verify=False, timeout=10)
    print("CRBR 1:", res.status_code, res.text[:200])
except Exception as e:
    print("CRBR 1 Error:", e)

try:
    res2 = requests.post(f"https://crbr.podatki.gov.pl/api/search/findByNip", json={"nip": nip}, verify=False, timeout=10)
    print("CRBR 2:", res2.status_code, res2.text[:200])
except Exception as e:
    pass

# Test RDF
print("\n--- Testing RDF API ---")
try:
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }
    rdf_url = "https://ekrs.ms.gov.pl/rdf/pd/search_df"
    res = requests.post(rdf_url, json={"krs": krs}, headers=headers, verify=False, timeout=10)
    print("RDF POST pd/search_df:", res.status_code)
    if res.status_code == 200:
        print(res.text[:500])
except Exception as e:
    print("RDF Error:", e)
