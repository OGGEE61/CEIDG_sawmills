import pandas as pd
import sys

def main():
    print("Loading data...")
    ceidg_df = pd.read_csv("data/processed/tartaki_ceidg.csv", low_memory=False, on_bad_lines='skip')
    krs_df = pd.read_csv("data/processed/tartaki_full_unfiltered.csv")
    print(f"Loaded {len(krs_df)} companies.")
    
    # 2. Build postal code to region mapping from CEIDG
    kod_mapping = {}
    for _, row in ceidg_df.iterrows():
        kod = row.get('detail.adresDzialalnosci.kod')
        woj = row.get('detail.adresDzialalnosci.wojewodztwo')
        powiat = row.get('detail.adresDzialalnosci.powiat')
        gmina = row.get('detail.adresDzialalnosci.gmina')
        
        if pd.notna(kod) and pd.notna(woj):
            if kod not in kod_mapping:
                kod_mapping[kod] = (woj, powiat, gmina)
    
    # 3. Enrich KRS data
    enriched_count = 0
    for idx, row in krs_df.iterrows():
        if pd.isna(row['voivodeship']) or row['voivodeship'] == '':
            kod = row.get('postal_code')
            if pd.notna(kod) and kod in kod_mapping:
                woj, powiat, gmina = kod_mapping[kod]
                krs_df.at[idx, 'voivodeship'] = woj
                krs_df.at[idx, 'county'] = powiat
                krs_df.at[idx, 'municipality'] = gmina
                enriched_count += 1
            else:
                # Basic fallback based on prefix
                if pd.notna(kod):
                    prefix = str(kod)[:2]
                    fallback = None
                    if prefix in ['00','01','02','03','04','05','06','07','08','09']: fallback = 'MAZOWIECKIE'
                    elif prefix in ['10','11','12','13','14','19']: fallback = 'WARMIŃSKO-MAZURSKIE'
                    elif prefix in ['15','16','17','18']: fallback = 'PODLASKIE'
                    elif prefix in ['20','21','22','23','24']: fallback = 'LUBELSKIE'
                    elif prefix in ['25','27','28','29']: fallback = 'ŚWIĘTOKRZYSKIE'
                    elif prefix == '26': fallback = 'MAZOWIECKIE' # Simplification
                    elif prefix in ['30','31','32','33','34']: fallback = 'MAŁOPOLSKIE'
                    elif prefix in ['35','36','37','38','39']: fallback = 'PODKARPACKIE'
                    elif prefix in ['40','41','42','43','44']: fallback = 'ŚLĄSKIE'
                    elif prefix in ['45','46','47','48','49']: fallback = 'OPOLSKIE'
                    elif prefix in ['50','51','52','53','54','55','56','57','58','59']: fallback = 'DOLNOŚLĄSKIE'
                    elif prefix in ['60','61','62','63','64']: fallback = 'WIELKOPOLSKIE'
                    elif prefix in ['65','66','67','68','69']: fallback = 'LUBUSKIE'
                    elif prefix in ['70','71','72','73','74','75','78','79']: fallback = 'ZACHODNIOPOMORSKIE'
                    elif prefix in ['76','77','80','81','82','83','84']: fallback = 'POMORSKIE'
                    elif prefix in ['85','86','87','88','89']: fallback = 'KUJAWSKO-POMORSKIE'
                    elif prefix in ['90','91','92','93','94','95','96','97','98','99']: fallback = 'ŁÓDZKIE'
                    
                    if fallback:
                        krs_df.at[idx, 'voivodeship'] = fallback
                        enriched_count += 1

    print(f"Enriched {enriched_count} records with voivodeship data.")
    
    krs_df.to_csv("data/processed/tartaki_full.csv", index=False)
    print("Done. Saved to data/processed/tartaki_full.csv")

if __name__ == "__main__":
    main()
