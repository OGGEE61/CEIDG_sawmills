import sys
from pathlib import Path
import json
import csv

# Add src to python path to import krs_tartaki
sys.path.append(str(Path("src").resolve()))
from krs_scraper.krs_tartaki import extract_company, OUTPUT_FIELDS

def main():
    raw_dir = Path("data/raw/raw_krs")
    out_csv = Path("data/processed/tartaki_full_unfiltered.csv")
    
    records = []
    if raw_dir.exists():
        for json_file in raw_dir.glob("*.json"):
            try:
                with json_file.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
                # Since we don't know the exact status_discovery from Candidates, we can leave it None
                row = extract_company(payload, source_status=None)
                if row.get("pkd_matches"):
                    records.append(row)
            except Exception as e:
                print(f"Error parsing {json_file}: {e}")
                
    print(f"Found {len(records)} verified companies in cache.")
    
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(records)
        
    print(f"Saved to {out_csv}")

if __name__ == "__main__":
    main()
