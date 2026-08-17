import json
import os
import re
from pathlib import Path
import pandas as pd
import streamlit as st
from datetime import datetime
import unicodedata
import geopandas as gpd
from dotenv import load_dotenv

DATA_DIR = Path("data/cache")
LIBRARY_DATA_ROOT = Path("data/libraries")

load_dotenv(override=True)


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "ja", "on"}


def _sanitize_library_id(value):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip())
    return cleaned.strip("_") or "default"


def _parse_library_keys():
    """
    Liest DASHBOARD_LIBRARY_KEYS aus .env.

    Erwartete Form:
    DASHBOARD_LIBRARY_KEYS=seengen=sehr_langer_key,musterhausen=anderer_key
    """
    raw = os.getenv("DASHBOARD_LIBRARY_KEYS", "").strip()
    key_to_library = {}

    if not raw:
        return key_to_library

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for library_id, access_key in parsed.items():
                if access_key:
                    key_to_library[str(access_key).strip()] = _sanitize_library_id(library_id)
            return key_to_library
    except json.JSONDecodeError:
        pass

    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        separator = "=" if "=" in item else ":"
        if separator not in item:
            continue
        library_id, access_key = item.split(separator, 1)
        library_id = _sanitize_library_id(library_id)
        access_key = access_key.split(" #", 1)[0].strip()
        if library_id and access_key:
            key_to_library[access_key] = library_id

    return key_to_library


def get_library_context():
    """
    Bestimmt die aktive Bibliothek aus dem URL-Parameter access_key.
    Ohne konfigurierte Keys bleibt der bisherige lokale data/cache-Modus aktiv.
    """
    query_access_key = st.query_params.get("access_key")
    if isinstance(query_access_key, list):
        query_access_key = query_access_key[0] if query_access_key else None
    query_access_key = str(query_access_key).strip() if query_access_key else None

    existing_context = st.session_state.get("library_context")
    if (
        existing_context
        and existing_context.get("authenticated")
        and not query_access_key
    ):
        return existing_context

    key_to_library = _parse_library_keys()
    require_access_key = _env_flag("DASHBOARD_REQUIRE_ACCESS_KEY", False)
    default_library = _sanitize_library_id(
        os.getenv("DASHBOARD_DEFAULT_LIBRARY_ID")
        or os.getenv("FILEMAKER_DATABASE")
        or "local"
    )

    authenticated = False
    if key_to_library:
        if query_access_key in key_to_library:
            library_id = key_to_library[query_access_key]
            authenticated = True
        elif require_access_key:
            st.error("Kein gueltiger Dashboard-Zugriff.")
            st.stop()
        else:
            library_id = default_library
    else:
        if require_access_key:
            st.error("Dashboard-Zugriff ist nicht konfiguriert.")
            st.stop()
        library_id = default_library

    data_root = Path(os.getenv("DASHBOARD_LIBRARY_DATA_ROOT", str(LIBRARY_DATA_ROOT)))
    cache_dir = data_root / library_id / "cache"

    # Lokale Entwicklung: bestehende Installationen mit data/cache laufen weiter.
    if not require_access_key and not cache_dir.exists() and DATA_DIR.exists():
        cache_dir = DATA_DIR

    context = {
        "library_id": library_id,
        "library_name": os.getenv(f"DASHBOARD_LIBRARY_NAME_{library_id.upper()}", library_id),
        "cache_dir": cache_dir,
        "authenticated": authenticated,
        "_access_key": query_access_key,
    }
    st.session_state["library_context"] = context
    return context


def normalize_media_id(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\D+", "", str(value)).strip()

def get_latest_file(pattern_prefix, data_dir=None):
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    if not data_dir.exists():
        return None
    files = list(data_dir.glob(f"{pattern_prefix}*.json"))
    if not files:
        return None
    def extract_date(filepath):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", filepath.name)
        if match:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        return datetime.min
    files.sort(key=extract_date, reverse=True)
    return files[0]

def get_file_metadata(filepath):
    """
    Liest Metadaten aus Cache-Datei:
    - Dateiname
    - Datenstand aus Dateinamen
    - cached_at aus JSON
    """
    metadata = {
        "file": filepath.name,
        "data_date": None,
        "cached_at": None,
        "status": "loaded",
    }

    # Datum aus Dateinamen
    match = re.search(r"(\d{4}-\d{2}-\d{2})", filepath.name)
    if match:
        metadata["data_date"] = match.group(1)

    # cached_at aus JSON
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            cache = json.load(f)

        metadata["cached_at"] = cache.get("cached_at")

    except Exception:
        pass

    return metadata


def get_source_metadata(status, message=None, filepath=None):
    metadata = {
        "file": filepath.name if filepath else None,
        "data_date": None,
        "cached_at": None,
        "status": status,
    }
    if message:
        metadata["message"] = message
    return metadata
def parse_date(series):
    return pd.to_datetime(series, errors="coerce", format="%m/%d/%Y")

def parse_datetime(series):
    return pd.to_datetime(series, errors="coerce", format="%m/%d/%Y %H:%M:%S")


def load_catalog_like_cache(pattern_prefix, data_dir=None):
    cache_file = get_latest_file(pattern_prefix, data_dir)
    if not cache_file:
        return None, None

    with open(cache_file, "r", encoding="utf-8") as f:
        cache = json.load(f)

    rows = []
    for record in cache.get("records", []):
        row = record.get("fieldData", {}).copy()

        if "NR Zugang" in row:
            rows.append(row)

    if not rows:
        return None, cache_file

    df = pd.DataFrame(rows)
    df["NR Zugang"] = (
        df["NR Zugang"]
        .astype(str)
        .str.strip()
    )
    df["_NR Zugang Match"] = df["NR Zugang"].apply(normalize_media_id)
    df = df[df["_NR Zugang Match"] != ""].copy()
    df = df.drop_duplicates(subset="_NR Zugang Match")

    return df, cache_file


def load_generic_cache(pattern_prefix, data_dir=None):
    cache_file = get_latest_file(pattern_prefix, data_dir)
    if not cache_file:
        return pd.DataFrame(), None

    with open(cache_file, "r", encoding="utf-8") as f:
        cache = json.load(f)

    rows = []
    for record in cache.get("records", []):
        row = record.get("fieldData", {}).copy()
        row["recordId"] = record.get("recordId")
        rows.append(row)

    return pd.DataFrame(rows), cache_file

def load_data():
    context = get_library_context()
    return _load_data_cached(str(context["cache_dir"]), context["library_id"])


@st.cache_data(ttl=3600) # Cache für 1 Stunde
def _load_data_cached(cache_dir, library_id):
    """
    Lädt alle Datenquellen.

    Rückgabe:
    {
        "loans": DataFrame,
        "catalog": DataFrame,
        "users": DataFrame,
        "smartlibrary": DataFrame,
        "metadata": {...}
    }
    """
    
    cache_dir = Path(cache_dir)

    # 1. Ergebnis-Dictionary initialisieren
    result = {
        "loans": pd.DataFrame(),
        "catalog": pd.DataFrame(),
        "antiquariat": pd.DataFrame(),
        "users": pd.DataFrame(),
        "smartlibrary": pd.DataFrame(),
        "preferences": pd.DataFrame(),
        "metadata": {},
        "library": {
            "id": library_id,
            "cache_dir": str(cache_dir),
        },
    }


    # --- 3. Ausleihdaten laden ---
    ausleihe_file = get_latest_file("Ausleihe_Liste_", cache_dir)
    if ausleihe_file:
        # WICHTIG: Datum extrahieren und speichern
        result["metadata"]["loans"] = get_file_metadata(ausleihe_file)
        
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

            datetime_columns = ["geändert", "geaendert", "Geändert"]
            for col in datetime_columns:
                if col in df_loans.columns:
                    df_loans[col] = parse_datetime(df_loans[col])
            
            # Numerische Felder
            numeric_columns = ["Verlängerung_Anz", "Anz_Exemplare", "Stat_Ausl_inkl_Verl"]
            for col in numeric_columns:
                if col in df_loans.columns:
                    df_loans[col] = pd.to_numeric(df_loans[col], errors="coerce").fillna(0)
            
            result["loans"] = df_loans
        except Exception as e:
            result["metadata"]["loans"] = get_source_metadata("error", f"Fehler beim Laden der Ausleihdaten: {e}", ausleihe_file)
            result["loans"] = pd.DataFrame()
    else:
        result["metadata"]["loans"] = get_source_metadata("missing", "Keine Ausleih-Datei im Cache gefunden.")

    # --- 4. Katalogdaten laden ---
    try:
        df_catalog, katalog_file = load_catalog_like_cache("Katalogisieren_", cache_dir)
        if katalog_file:
            result["metadata"]["catalog"] = get_file_metadata(katalog_file)
            result["catalog"] = df_catalog if df_catalog is not None else pd.DataFrame()
            if df_catalog is None or df_catalog.empty:
                result["metadata"]["catalog"]["status"] = "empty"
                result["metadata"]["catalog"]["message"] = "Katalogdatei gefunden, aber keine Datensaetze enthalten."
        else:
            result["metadata"]["catalog"] = get_source_metadata("missing", "Keine Katalog-Datei im Cache gefunden.")
    except Exception as e:
        result["metadata"]["catalog"] = get_source_metadata("error", f"Fehler beim Laden der Katalogdaten: {e}")
        result["catalog"] = pd.DataFrame()

    # --- 4b. Antiquariat laden (ausgeschiedene Medien fuer historische Ausleihen) ---
    try:
        df_antiquariat, antiquariat_file = load_catalog_like_cache("Antiquariat_", cache_dir)
        if antiquariat_file:
            result["metadata"]["antiquariat"] = get_file_metadata(antiquariat_file)
            result["antiquariat"] = df_antiquariat if df_antiquariat is not None else pd.DataFrame()
            if df_antiquariat is None or df_antiquariat.empty:
                result["metadata"]["antiquariat"]["status"] = "empty"
                result["metadata"]["antiquariat"]["message"] = "Antiquariatsdatei gefunden, aber keine Datensaetze enthalten."
        else:
            result["metadata"]["antiquariat"] = get_source_metadata("missing", "Keine Antiquariat-Datei im Cache gefunden.")
    except Exception as e:
        result["metadata"]["antiquariat"] = get_source_metadata("error", f"Fehler beim Laden der Antiquariatsdaten: {e}")
        result["antiquariat"] = pd.DataFrame()

    # --- 5. Nutzerdaten laden ---
    nutzer_file = get_latest_file("Benutzer_Dashboard_", cache_dir)

    if nutzer_file:
        result["metadata"]["users"] = get_file_metadata(nutzer_file)
        try:
            with open(nutzer_file, "r", encoding="utf-8") as f:
                cache_users = json.load(f)

            user_rows = [
                record.get("fieldData", {}).copy()
                for record in cache_users.get("records", [])
            ]

            if user_rows:
                df_users = pd.DataFrame(user_rows)

                if "Benutzergruppe" in df_users.columns:
                    df_users["Benutzergruppe"] = df_users["Benutzergruppe"].astype(str).str.strip()
                if "Wohnort" in df_users.columns:
                    df_users["Wohnort"] = df_users["Wohnort"].astype(str).str.strip()

                result["users"] = df_users
            else:
                result["metadata"]["users"]["status"] = "empty"
                result["metadata"]["users"]["message"] = "Nutzerdatei gefunden, aber keine Datensaetze enthalten."
                result["users"] = pd.DataFrame()
        except Exception as e:
            result["metadata"]["users"] = get_source_metadata("error", f"Fehler beim Laden der Nutzerdaten: {e}", nutzer_file)
            result["users"] = pd.DataFrame()
    else:
        result["metadata"]["users"] = get_source_metadata("missing", "Keine Nutzer-Datei im Cache gefunden.")
    # --- 6. SmartLibrary-Protokoll laden ---
    smartlibrary_file = get_latest_file("SmartLibraryProtokoll_", cache_dir)

    if smartlibrary_file:
        result["metadata"]["smartlibrary"] = get_file_metadata(smartlibrary_file)
        try:
            with open(smartlibrary_file, "r", encoding="utf-8") as f:
                cache = json.load(f)

            rows = []
            for record in cache.get("records", []):
                row = record.get("fieldData", {}).copy()
                row["recordId"] = record.get("recordId")
                rows.append(row)

            if rows:
                df_smartlibrary = pd.DataFrame(rows)

                if "erstellt" in df_smartlibrary.columns:
                    df_smartlibrary["erstellt"] = parse_datetime(df_smartlibrary["erstellt"])

                if "Nummer" in df_smartlibrary.columns:
                    df_smartlibrary["Nummer"] = df_smartlibrary["Nummer"].astype(str).str.strip()

                result["smartlibrary"] = df_smartlibrary
            else:
                result["metadata"]["smartlibrary"]["status"] = "empty"
                result["metadata"]["smartlibrary"]["message"] = "SmartLibrary-Datei gefunden, aber keine Datensaetze enthalten."
                result["smartlibrary"] = pd.DataFrame()
        except Exception as e:
            result["metadata"]["smartlibrary"] = get_source_metadata("error", f"Fehler beim Laden der SmartLibrary-Daten: {e}", smartlibrary_file)
            result["smartlibrary"] = pd.DataFrame()
    else:
        result["metadata"]["smartlibrary"] = get_source_metadata("missing", "Keine SmartLibrary-Datei im Cache gefunden.")

    # --- 6b. Voreinstellungen laden (z.B. bediente Oeffnungszeiten pro Zweigstelle) ---
    try:
        df_preferences, preferences_file = load_generic_cache("Voreinstellungen_", cache_dir)
        if preferences_file:
            result["metadata"]["preferences"] = get_file_metadata(preferences_file)
            result["preferences"] = df_preferences
            if df_preferences.empty:
                result["metadata"]["preferences"]["status"] = "empty"
                result["metadata"]["preferences"]["message"] = "Voreinstellungen-Datei gefunden, aber keine Datensaetze enthalten."
        else:
            result["metadata"]["preferences"] = get_source_metadata("missing", "Keine Voreinstellungen-Datei im Cache gefunden.")
    except Exception as e:
        result["metadata"]["preferences"] = get_source_metadata("error", f"Fehler beim Laden der Voreinstellungen: {e}")
        result["preferences"] = pd.DataFrame()

    # --- 7. Join von Ausleihe und Katalog ---
    catalog_sources = [
        df for df in [result["catalog"], result["antiquariat"]]
        if df is not None and not df.empty
    ]

    if result["loans"] is not None and catalog_sources:
        df_loans = result["loans"]
        df_catalog = (
            pd.concat(catalog_sources, ignore_index=True)
            .drop_duplicates(subset="_NR Zugang Match", keep="first")
        )
        
        id_col = "NR Zugang"
        if id_col in df_loans.columns:
            df_loans[id_col] = df_loans[id_col].astype(str).str.strip()
            df_loans["_NR Zugang Match"] = df_loans[id_col].apply(normalize_media_id)
            df_joined = (
                df_loans.merge(
                df_catalog, 
                on="_NR Zugang Match", 
                how="left",
                suffixes=("_loan", "_catalog"))
                .drop(columns=["_NR Zugang Match"])
            )

            if "NR Zugang_loan" in df_joined.columns:
                df_joined["NR Zugang"] = df_joined["NR Zugang_loan"]
                df_joined = df_joined.drop(columns=["NR Zugang_loan"])

            if "NR Zugang_catalog" in df_joined.columns:
                df_joined = df_joined.drop(columns=["NR Zugang_catalog"])

            result["loans"] = df_joined
            

    return result

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

