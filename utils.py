import json
import re
from pathlib import Path
import pandas as pd
import streamlit as st
from datetime import datetime
import unicodedata
import geopandas as gpd

DATA_DIR = Path("data/cache")

def get_latest_file(pattern_prefix):
    if not DATA_DIR.exists():
        return None
    files = list(DATA_DIR.glob(f"{pattern_prefix}*.json"))
    if not files:
        return None
    def extract_date(filepath):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", filepath.name)
        if match:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        return datetime.min
    files.sort(key=extract_date, reverse=True)
    return files[0]

def parse_date(series):
    return pd.to_datetime(series, errors="coerce", format="%m/%d/%Y")

def parse_datetime(series):
    return pd.to_datetime(series, errors="coerce", format="%m/%d/%Y %H:%M:%S")

@st.cache_data (ttl=3600) #Cache für 1 Stunde
def load_data():
    """
    Lädt Ausleih-, Katalog- und Nutzerdaten.
    Gibt ein Dictionary zurück: {'loans': df, 'catalog': df, 'users': df}
    """
    result = {
        "loans": None,
        "catalog": None,
        "users": None
    }

    # --- 1. Ausleihdaten laden ---
    ausleihe_file = get_latest_file("Ausleihe_Liste_")
    if ausleihe_file:
        try:
            with open(ausleihe_file, "r", encoding="utf-8") as f:
                cache_loans = json.load(f)
            records = cache_loans.get("records", [])
            rows = []
            for record in records:
                row = record.get("fieldData", {}).copy()
                row["recordId"] = record.get("recordId")
                rows.append(row)
            
            df_loans = pd.DataFrame(rows)
            
            # Datumsfelder konvertieren
            date_columns = ["Ausleihdatum", "Rückgabedatum", "Ausleihe bis", "Mahndatum 0", "Mahndatum 1", "Mahndatum 2", "Mahndatum 3", "RG_Datum"]
            for col in date_columns:
                if col in df_loans.columns:
                    df_loans[col] = parse_date(df_loans[col])
            
            # Numerische Felder
            numeric_columns = ["Verlängerung_Anz", "Anz_Exemplare", "Stat_Ausl_inkl_Verl"]
            for col in numeric_columns:
                if col in df_loans.columns:
                    df_loans[col] = pd.to_numeric(df_loans[col], errors="coerce").fillna(0)
            
            result["loans"] = df_loans
        except Exception as e:
            st.error(f"Fehler beim Laden der Ausleihdaten: {e}")
    else:
        st.warning("Keine Ausleih-Daten gefunden (Erwartetes Muster: 'Ausleihe_Liste_YYYY-MM-DD.json').")

    # --- 2. Katalogdaten laden (für Medieninfos/Cover) ---
    katalog_file = get_latest_file("Katalogisieren_")
    if katalog_file:
        try:
            with open(katalog_file, "r", encoding="utf-8") as f:
                cache_kat = json.load(f)
            kat_records = cache_kat.get("records", [])
            kat_rows = []
            for record in kat_records:
                row = record.get("fieldData", {}).copy()
                if "NR Zugang" in row: 
                    kat_rows.append(row)
            
            if kat_rows:
                df_catalog = pd.DataFrame(kat_rows)
                if "NR Zugang" in df_catalog.columns and "URL_Cover" in df_catalog.columns:
                    df_catalog = df_catalog[["NR Zugang", "URL_Cover"]].drop_duplicates()
                    # Sicherstellen, dass NR Zugang String ist für den Join
                    df_catalog["NR Zugang"] = df_catalog["NR Zugang"].astype(str).str.strip()
                else:
                    st.warning("Felder 'NR Zugang' oder 'URL_Cover' im Katalog nicht gefunden.")
                    df_catalog = None
            else:
                df_catalog = None
            
            result["catalog"] = df_catalog
        except Exception as e:
            st.warning(f"Fehler beim Laden der Katalogdaten: {e}")

    # --- 3. Nutzerdaten laden (NEU: Wichtig für Benutzergruppe & Wohnort) ---
    # Hinweis: Passe das Präfix "Nutzer_" an, falls deine Datei anders heißt (z.B. "Benutzer_", "Adressen_")
    nutzer_file = get_latest_file("Benutzer_Dashboard_") 
    
    if nutzer_file:
        try:
            with open(nutzer_file, "r", encoding="utf-8") as f:
                cache_users = json.load(f)
            user_records = cache_users.get("records", [])
            user_rows = []
            for record in user_records:
                row = record.get("fieldData", {}).copy()
                user_rows.append(row)
            
            if user_rows:
                df_users = pd.DataFrame(user_rows)
                
                # Wichtige Felder für den Datenqualitäts-Check sicherstellen
                # Wir trimmen hier schon mal grob Leerzeichen, damit der Check fair ist
                if "Benutzergruppe" in df_users.columns:
                    df_users["Benutzergruppe"] = df_users["Benutzergruppe"].astype(str).str.strip()
                if "Wohnort" in df_users.columns:
                    df_users["Wohnort"] = df_users["Wohnort"].astype(str).str.strip()
                    
                result["users"] = df_users
            else:
                st.warning("Nutzerdatei gefunden, aber keine Datensätze enthalten.")
        except Exception as e:
            st.error(f"Fehler beim Laden der Nutzerdaten: {e}")
    else:
        st.warning("Keine Nutzer-Daten gefunden (Erwartetes Muster: 'Nutzer_YYYY-MM-DD.json').")
        st.info("Hinweis: Der Datenqualitäts-Check für Benutzergruppen und Wohnorte benötigt diese Datei.")

    # --- 4. Join von Ausleihe und Katalog (Optional, falls für Analyse benötigt) ---
    # Dies ändern wir nicht im Return-Dict, sondern fügen es dem Loans-DF hinzu, falls Katalog da ist
    if result["loans"] is not None and result["catalog"] is not None:
        df_loans = result["loans"]
        df_catalog = result["catalog"]
        
        id_col = "NR Zugang"
        if id_col in df_loans.columns:
            df_loans[id_col] = df_loans[id_col].astype(str).str.strip()
            result["loans"] = df_loans.merge(df_catalog, on=id_col, how="left")

    return result

# ---------------------------------------------------------
# HIER MUSS DIE FUNKTION STEHEN
# ---------------------------------------------------------
def apply_config(df, config):
    """
    Wendet Mapping-Regeln aus der config.json auf den DataFrame an.
    Erstellt eine neue Spalte 'Benutzergruppe_Gruppiert'.
    """
    # Wenn keine Daten oder keine Config, nichts tun
    if df is None or df.empty or not config:
        return df
    
    df_work = df.copy()
    
    # 1. Benutzergruppen mappen
    # Prüfen ob Mapping-Regeln existieren UND die Spalte "Benutzergruppe" da ist
    if "group_mapping" in config and config["group_mapping"] and "Benutzergruppe" in df_work.columns:
        mapping_rules = config["group_mapping"]
        
        def map_group(val):
            if pd.isna(val):
                return "Unbekannt" # Oder pd.NA, je nach Wunsch
            val_str = str(val).strip()
            # Prüfen ob der Wert in einer der Listen vorkommt
            for new_name, source_list in mapping_rules.items():
                if val_str in source_list:
                    return new_name
            return val_str # Wenn nicht gemappt, bleibt der alte Name stehen
            
        # WICHTIG: Hier wird eine NEUE Spalte erstellt, nicht die alte überschrieben!
        df_work["Benutzergruppe_Gruppiert"] = df_work["Benutzergruppe"].apply(map_group)

    return df_work

def apply_filters(df, date_range, selected_zweigstellen, selected_medienarten, selected_benutzergruppen, selected_kategorie_alter, nur_erstausleihen=False):
    """
    Filtert den DataFrame.
    nur_erstausleihen: Wenn True, werden alle Zeilen entfernt, wo Verlängerung_Anz > 0 ist.
    """
    if df is None or df.empty:
        return df
        
    filtered = df.copy()
    
    # --- NEU: Filter für Verlängerungen ---
    if nur_erstausleihen:
        if "Verlängerung_Anz" in filtered.columns:
            filtered = filtered[filtered["Verlängerung_Anz"] == 0]
        else:
            st.warning("Feld 'Verlängerung_Anz' nicht gefunden. Filter kann nicht angewendet werden.")
    # --------------------------------------

    # Datumsfilter
    if date_range and len(date_range) == 2 and "Ausleihdatum" in filtered.columns:
        start_date = pd.to_datetime(date_range[0])
        end_date = pd.to_datetime(date_range[1])
        filtered = filtered[
            (filtered["Ausleihdatum"] >= start_date)
            & (filtered["Ausleihdatum"] <= end_date)
        ]

    # Zweigstelle
    if selected_zweigstellen and "Zweigstelle" in filtered.columns:
        filtered = filtered[filtered["Zweigstelle"].astype(str).isin(selected_zweigstellen)]
        
    # Medienart
    if selected_medienarten and "Medienart" in filtered.columns:
        filtered = filtered[filtered["Medienart"].astype(str).isin(selected_medienarten)]
        
    # --- BENUTZERGRUPPE: Dynamische Spaltenwahl ---
    if selected_benutzergruppen:
        # Prüfen, ob die gruppierte Spalte existiert (nach apply_group_mapping)
        if "Benutzergruppe_Gruppiert" in filtered.columns:
            target_col = "Benutzergruppe_Gruppiert"
        else:
            # Fallback auf die Originalspalte, falls Mapping nicht lief
            target_col = "Benutzergruppe"
            
        if target_col in filtered.columns:
            filtered = filtered[filtered[target_col].astype(str).isin(selected_benutzergruppen)]
        else:
            st.warning(f"Spalte {target_col} nicht gefunden.")
    # -------------------------------------------

    # Kategorie Alter
    if selected_kategorie_alter and "Kategorie Alter" in filtered.columns:
        filtered = filtered[filtered["Kategorie Alter"].astype(str).isin(selected_kategorie_alter)]
        
    return filtered

def apply_group_mapping(df, config):
    """
    Wendet das group_mapping aus der Config auf den DataFrame an.
    Erstellt eine neue Spalte 'Benutzergruppe_Gruppiert'.
    """
    group_mapping = config.get("group_mapping", {})
    
    if not group_mapping:
        return df

    # Kopie des DataFrames erstellen, um SettingWithCopyWarning zu vermeiden
    df_mapped = df.copy()
    
    # Ziel-Spalte initialisieren (z.B. mit dem Originalwert oder 'Unbekannt')
    # Wir nehmen hier den Originalwert als Fallback
    df_mapped['Benutzergruppe_Gruppiert'] = df_mapped['Benutzergruppe']

    # Durch das Mapping iterieren
    # Struktur: { "Zielgruppe": ["Original A", "Original B"], ... }
    for target_group, source_values in group_mapping.items():
        # Maske erstellen: Wo ist die Benutergruppe in der Liste der source_values?
        mask = df_mapped['Benutzergruppe'].isin(source_values)
        # Werte überschreiben
        df_mapped.loc[mask, 'Benutzergruppe_Gruppiert'] = target_group

    return df_mapped


def normalize_text(text):
    """
    Normalisiert Text für den Vergleich:
    - Grossbuchstaben
    - Entfernt Leerzeichen vorne/hinten
    - Ersetzt Umlaute (ä -> ae) falls nötig, oder behält sie bei (hier: behält bei, aber macht klein)
    """
    if pd.isna(text):
        return ""
    text = str(text).strip().lower()
    # Optional: Umlaute normalisieren, falls die CSV anders kodiert ist
    # text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    return text


@st.cache_data (ttl=86400) #Cache für 24 Stunden (Ortsliste ändert sich nicht)
def load_swiss_locations(csv_path="data/swiss_locations.csv"):
    """
    Lädt die offizielle CH-Ortschaften-Liste.
    Erwartete Spalten: Ortschaftsname, PLZ4, Gemeindename
    WICHTIG: Gibt auch 'Ort_Norm' zurück, damit die Rückwärtssuche funktioniert.
    """
    if not Path(csv_path).exists():
        st.warning(f"Referenzdatei {csv_path} nicht gefunden. Orts-Check deaktiviert.")
        return None
    
    try:
        # CSV laden
        df_ref = pd.read_csv(csv_path, sep=';', dtype={'PLZ4': str})
        
        # Basis-Spalten vorbereiten
        df_ref['Ort_Roh'] = df_ref['Ortschaftsname']
        df_ref['PLZ_Roh'] = df_ref['PLZ4'].astype(str).str.zfill(4) # Sicherstellen, dass 4 Stellen
        
        # Normalisierte Spalten für den Join und die Suche
        df_ref['Ort_Norm'] = df_ref['Ortschaftsname'].apply(normalize_text)
        df_ref['Key_Norm'] = df_ref['PLZ_Roh'] + "_" + df_ref['Ort_Norm']
        
        # Offizieller Ort für die Anzeige/Korrektur
        df_ref['Offizieller_Ort'] = df_ref['Ortschaftsname'] 
        
        # WICHTIG: Wir geben jetzt 'Ort_Norm' mit zurück, damit validate_and_clean_locations darauf zugreifen kann
        return df_ref[['Key_Norm', 'PLZ_Roh', 'Ort_Roh', 'Ort_Norm', 'Offizieller_Ort', 'Gemeindename', 'Kantonskürzel']]
    except Exception as e:
        st.error(f"Fehler beim Laden der Ortsliste: {e}")
        return None

# In utils.py hinzufügen/ersetzen

def get_similarity_score(s1, s2):
    """
    Einfacher Ähnlichkeits-Score ohne externe Bibliotheken.
    Gibt 1.0 bei perfekter Übereinstimmung, 0.0 bei keiner.
    Nutzt einfache Logik: Ist s1 in s2 enthalten oder umgekehrt?
    """
    s1 = s1.lower()
    s2 = s2.lower()
    if s1 == s2:
        return 1.0
    if s1 in s2 or s2 in s1:
        return 0.8
    # Einfache Zeichenübereinstimmung für Tippfehler (sehr basal)
    common = len(set(s1) & set(s2))
    return common / max(len(s1), len(s2), 1)

@st.cache_data(ttl=3600)
def validate_and_clean_locations(df_users, df_ref):
    """
    Erweiterte Prüfung:
    1. Exakter Match (PLZ + Ort)
    2. PLZ bekannt -> Ort ähnlich? (Vorschlag: Korrektur Ort)
    3. PLZ unbekannt -> Ort bekannt? (Vorschlag: Korrektur PLZ)
    4. Beides falsch -> Ähnlichster Ort in der ganzen CH (Fallback)
    """
    if df_ref is None or df_users is None:
        return df_users, pd.DataFrame()

    df_work = df_users.copy()
    
    # Vorbereitung
    df_work['PLZ_Str'] = df_work.get('PLZ', '').astype(str).str.zfill(4).str.strip()
    df_work['Ort_Roh'] = df_work.get('Wohnort', '').astype(str).str.strip()
    
    validierte_orte = []
    kanton_liste = []
    match_status = []
    fehler_liste = [] 

    # Indizes für schnellen Zugriff vorbereiten
    # 1. Nach PLZ gruppieren (für Fall: PLZ ist richtig, Ort falsch)
    ref_by_plz = df_ref.groupby('PLZ_Roh').apply(lambda x: x.to_dict('records')).to_dict()
    
    # 2. Nach Ort normalisiert gruppieren (für Fall: Ort ist richtig, PLZ falsch)
    # Da es Orte mit gleichem Namen aber verschiedener PLZ geben kann (z.B. Zürich hat viele), speichern wir alle
    ref_by_ort = df_ref.groupby('Ort_Norm').apply(lambda x: x.to_dict('records')).to_dict()

    for index, row in df_work.iterrows():
        plz = row['PLZ_Str']
        ort_raw = row['Ort_Roh']
        ort_norm = normalize_text(ort_raw)
        
        # --- 1. Exakter Match ---
        match = df_ref[df_ref['Key_Norm'] == f"{plz}_{ort_norm}"]
        if not match.empty:
            validierte_orte.append(match.iloc[0]['Offizieller_Ort'])
            kanton_liste.append(match.iloc[0]['Kantonskürzel'])
            match_status.append('✅ OK')
            continue

        best_candidate = None
        best_score = 0
        error_type = ""
        vorschlag_text = ""

        # --- 2. PLZ ist bekannt, Ort weicht ab? ---
        if plz in ref_by_plz:
            candidates = ref_by_plz[plz]
            for cand in candidates:
                score = get_similarity_score(ort_norm, normalize_text(cand['Ort_Roh']))
                if score > best_score:
                    best_score = score
                    best_candidate = cand
            
            if best_score > 0.5:
                # Wir haben einen Treffer basierend auf der PLZ
                validierte_orte.append(best_candidate['Offizieller_Ort'])
                kanton_liste.append(best_candidate['Kantonskürzel'])
                match_status.append('⚠️ Ort korrigiert')
                error_type = f"Ort weicht ab ({best_score:.0%})"
                vorschlag_text = f"{best_candidate['Offizieller_Ort']} ({plz})"
                # Eintrag in Fehlerliste
                fehler_liste.append({
                    "PLZ": plz, "Eingegebener Ort": ort_raw, 
                    "Vorschlag": vorschlag_text, "Grund": error_type, 
                    "priority_score": best_score
                })
                continue

        # --- 3. PLZ unbekannt, aber Ortname bekannt? (Rückwärtssuche) ---
        # Wir suchen den eingegebenen Ort in der gesamten Referenzliste
        if ort_norm in ref_by_ort:
            candidates = ref_by_ort[ort_norm]
            # Wenn es mehrere PLZ für diesen Ort gibt (z.B. Lausanne), nehmen wir die erste oder alle als Vorschlag
            # Hier nehmen wir den ersten Treffer als Hauptvorschlag, erwähnen aber weitere im Text wenn nötig
            best_candidate = candidates[0] 
            best_score = 0.9 # Hoher Score, da Ort exakt übereinstimmt
            
            validierte_orte.append(best_candidate['Offizieller_Ort'])
            kanton_liste.append(best_candidate['Kantonskürzel'])
            match_status.append('⚠️ PLZ korrigiert')
            
            # Text bauen: "1000 Lausanne" (wenn mehrere PLZ, könnte man "Mehrere PLZ möglich" schreiben)
            plz_vorschlag = best_candidate['PLZ_Roh']
            vorschlag_text = f"{plz_vorschlag} {best_candidate['Offizieller_Ort']}"
            error_type = "PLZ unbekannt, Ort korrekt"
            
            fehler_liste.append({
                "PLZ": plz, "Eingegebener Ort": ort_raw, 
                "Vorschlag": vorschlag_text, "Grund": error_type, 
                "priority_score": 0.9 # Hoher Score = niedrige Priorität (unten in Liste)
            })
            continue

        # --- 4. Beides falsch? (Globaler Ähnlichkeits-Check als Fallback) ---
        # Nur wenn PLZ und Ort beide nicht passen. Wir suchen den ähnlichsten Ort in der GANZEN Liste.
        # Achtung: Rechenintensiv! Wir beschränken uns hier auf eine einfache Logik oder lassen es weg, wenn zu langsam.
        # Für dieses Beispiel machen wir einen simplen Check: Gibt es einen Ort, der sehr ähnlich ist?
        
        global_best_score = 0
        global_best_cand = None
        
        # Wir iterieren nicht über ALLE, sondern nur über einzigartige Ortsnamen, um Zeit zu sparen
        # Oder wir lassen diesen Schritt weg, wenn die Performance leidet. 
        # Alternative: Wir melden es einfach als "Unbekannt".
        # Für den Anfang: Meldung als Unbekannt mit höchster Priorität.
        
        validierte_orte.append(ort_raw)
        kanton_liste.append(None)
        match_status.append('❌ Unbekannt')
        
        fehler_liste.append({
            "PLZ": plz, "Eingegebener Ort": ort_raw, 
            "Vorschlag": "Manuelle Prüfung (PLZ & Ort unbekannt)", 
            "Grund": "Keine Übereinstimmung gefunden", 
            "priority_score": 0.0 # Ganz nach oben!
        })

    # DataFrames zuweisen
    df_work['Ort_Validiert'] = validierte_orte
    df_work['Kanton'] = kanton_liste
    df_work['Ort_Match_Status'] = match_status
    
    # Sortieren und zurückgeben
    df_fehler = pd.DataFrame(fehler_liste)
    if not df_fehler.empty:
        df_fehler = df_fehler.sort_values(by="priority_score", ascending=True)
        df_fehler = df_fehler.drop(columns=["priority_score"])

    return df_work, df_fehler

@st.cache_data(show_spinner="🔍 Führe geografische Validierung durch (kann beim ersten Mal etwas dauern)...")
def run_validation_pipeline(users_df, ref_df):
    """
    Wrapper-Funktion, die die Validierung cached.
    Streamlit prüft den Hash von users_df und ref_df. 
    Wenn sich die Daten nicht geändert haben, wird das gespeicherte Ergebnis zurückgegeben.
    """
    if users_df is None or ref_df is None:
        return users_df, pd.DataFrame()
    
    # Hier rufen wir deine eigentliche, schwere Funktion auf
    return validate_and_clean_locations(users_df, ref_df)

@st.cache_data(ttl=86400) # 24 Stunden Cache
def load_shapefile_cached(shp_path):
    """Lädt das Shapefile und cached es im Speicher."""
    return gpd.read_file(shp_path)