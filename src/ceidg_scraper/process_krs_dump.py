import pandas as pd
import argparse
import sys
import os

def normalize_column_name(col):
    return str(col).lower().strip()

def find_col(columns, keywords):
    for col in columns:
        col_norm = normalize_column_name(col)
        for kw in keywords:
            if kw in col_norm:
                return col
    return None

def main():
    parser = argparse.ArgumentParser(description="Przetwarzanie zrzutu KRS/REGON CSV z dane.gov.pl")
    parser.add_argument("input_file", help="Ścieżka do pobranego pliku CSV z dane.gov.pl")
    parser.add_argument("--sep", default=";", help="Separator w pliku CSV (domyślnie: średnik, ale czasem to przecinek ',')")
    parser.add_argument("--encoding", default="utf-8", help="Kodowanie pliku CSV (domyślnie: utf-8, ew. cp1250)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"Błąd: Plik {args.input_file} nie istnieje.")
        sys.exit(1)
        
    print(f"Rozpoczynam analizę pliku: {args.input_file} ...")
    
    try:
        df_head = pd.read_csv(args.input_file, sep=args.sep, encoding=args.encoding, nrows=5, dtype=str)
    except UnicodeDecodeError:
        print("Błąd kodowania utf-8. Próbuję cp1250 (standard Windows)...")
        args.encoding = "cp1250"
        df_head = pd.read_csv(args.input_file, sep=args.sep, encoding=args.encoding, nrows=5, dtype=str)
    except Exception as e:
        print(f"Błąd odczytu nagłówków. Spróbuj zmienić separator np. --sep \",\": {e}")
        sys.exit(1)
        
    cols = df_head.columns.tolist()
    print("Znaleziono kolumny w pliku zrzutu:", cols)
    
    # Heurystyka do znajdowania nazw kolumn, ponieważ GUS często je zmienia
    col_krs = find_col(cols, ["krs"])
    col_nip = find_col(cols, ["nip"])
    col_regon = find_col(cols, ["regon"])
    col_nazwa = find_col(cols, ["nazwa"])
    col_woj = find_col(cols, ["wojew"])
    col_miasto = find_col(cols, ["miejscow", "miasto"])
    col_kod = find_col(cols, ["kod"])
    col_ulica = find_col(cols, ["ulica"])
    col_budynek = find_col(cols, ["dom", "budynek", "posesj"])
    col_pkd = find_col(cols, ["pkd", "działalno", "dzialalno", "klasyfikacj"])
    
    if not col_pkd:
        print("\nBŁĄD: Nie potrafię automatycznie znaleźć kolumny z kodami PKD w tym pliku!")
        print("Dostępne kolumny to:", cols)
        sys.exit(1)
        
    print("\nDopasowano kolumny do naszych potrzeb:")
    print(f"KRS: {col_krs} | NIP: {col_nip} | REGON: {col_regon}")
    print(f"Nazwa: {col_nazwa} | PKD: {col_pkd}")
    print(f"Adres: {col_ulica}, {col_budynek}, {col_kod} {col_miasto}, {col_woj}")
    print("-" * 50)
    
    chunksize = 100000
    total_processed = 0
    total_saved = 0
    
    output_rows = []
    
    for chunk in pd.read_csv(args.input_file, sep=args.sep, encoding=args.encoding, chunksize=chunksize, dtype=str, low_memory=False):
        total_processed += len(chunk)
        
        # Filtrujemy PKD ignorując kropki (16.10.Z == 1610Z)
        if col_pkd in chunk.columns:
            pkd_mask = chunk[col_pkd].str.replace(".", "", regex=False).str.contains("1610Z|1611Z", na=False, case=False)
            filtered = chunk[pkd_mask].copy()
            
            if not filtered.empty:
                for _, row in filtered.iterrows():
                    
                    # Ignorujemy osoby fizyczne prowadzące JDG jeśli taki rejestr to zawiera (mamy ich z CEIDG)
                    # Często w KRS nie ma JDG, ale w zrzutach REGON są wszyscy. JDG nie ma numeru KRS.
                    if col_krs and pd.isna(row.get(col_krs, float('nan'))) and "REGON" not in args.input_file.upper():
                        # Jeżeli plik nazywa się KRS, ale brakuje KRS, to podejrzane, ale zostawiamy.
                        pass
                        
                    out_row = {
                        "CEIDG_ID": str(row[col_krs]) if col_krs and pd.notna(row[col_krs]) else f"KRS_{row[col_regon] if col_regon else total_processed}",
                        "NAZWA": row[col_nazwa] if col_nazwa else "",
                        "NIP": row[col_nip] if col_nip else "",
                        "REGON": row[col_regon] if col_regon else "",
                        "STATUS": "AKTYWNY",
                        "PKD_GLOWNE_KOD": "1610Z" if "1610" in str(row[col_pkd]).replace(".", "") else "1611Z",
                        "PKD_GLOWNE_NAZWA": "Tartak (KRS)",
                        "detail.adresDzialalnosci.ulica": row[col_ulica] if col_ulica else "",
                        "detail.adresDzialalnosci.budynek": row[col_budynek] if col_budynek else "",
                        "detail.adresDzialalnosci.miasto": row[col_miasto] if col_miasto else "",
                        "detail.adresDzialalnosci.wojewodztwo": row[col_woj] if col_woj else "",
                        "detail.adresDzialalnosci.powiat": "",
                        "detail.adresDzialalnosci.gmina": "",
                        "detail.adresDzialalnosci.kod": row[col_kod] if col_kod else "",
                        "REJESTR": "KRS"
                    }
                    output_rows.append(out_row)
                total_saved += len(filtered)
                
        print(f"Przeanalizowano wierszy: {total_processed} | Znaleziono spółek: {total_saved}", end="\r")
        
    print(f"\n\nZakończono! Znaleziono łącznie: {total_saved} spółek (KRS).")
    
    if output_rows:
        df_out = pd.DataFrame(output_rows)
        # Usuwamy ewentualne duplikaty po numerze NIP (jeśli firma była w KRS i REGON podwójnie)
        df_out = df_out.drop_duplicates(subset=['NIP'], keep='first')
        
        out_file = "tartaki_krs.csv"
        df_out.to_csv(out_file, sep=";", index=False, encoding="utf-8-sig")
        print(f"Zapisano unikalne wyniki do pliku: {out_file}.")
    else:
        print("Nie znaleziono żadnych pasujących firm w pliku.")

if __name__ == "__main__":
    main()
