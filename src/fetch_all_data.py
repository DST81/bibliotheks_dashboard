import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Lade .env Datei explizit
load_dotenv()

# --- KONFIGURATION ---
SERVER = os.getenv("FILEMAKER_SERVER")
DATABASE = os.getenv("FILEMAKER_DATABASE")
USER = os.getenv("FILEMAKER_USER")
PASSWORD = os.getenv("FILEMAKER_PASSWORD")
SINGLE_LAYOUT = os.getenv("FILEMAKER_LAYOUT") # Der einzelne Layout Name aus .env
MODIFIED_FIELD = os.getenv("FILEMAKER_MODIFIED_FIELD", "geändert")

# Validierung der Umgebungsvariablen
if not all([SERVER, DATABASE, USER, PASSWORD]):
    raise ValueError("FEHLER: Eine oder mehrere Umgebungsvariablen (SERVER, DATABASE, USER, PASSWORD) fehlen in der .env Datei!")

# Bereinige Server URL (entferne trailing slash, um doppelte // zu vermeiden)
SERVER = SERVER.rstrip('/')

# Definiere die Liste der Layouts
# Option A: Nutze die hardcodierte Liste (empfohlen für den Multi-Export)
LAYOUTS = ["Ausleihe Liste", "SmartLibraryProtokoll", "Katalogisieren", "Benutzer_Dashboard"]

# Mapping: Welches Feld enthält das Änderungsdatum für welches Layout?
# Wenn ein Layout nicht aufgeführt ist, wird 'geändert' als Standard verwendet.
MODIFIED_FIELDS_MAP = {
    "Katalog": "Mutationsdatum",       # <--- Hier den exakten Namen eintragen
    "Ausleihe Liste": "geändert",      # Beispiel, falls das anders heißt
    "Benutzer_Dashboard": "geändert",  # Beispiel
    "SmartLibraryProtokoll": "erstellt" 
}

# Standard-Fallback, falls kein spezifischer Eintrag im Map existiert
DEFAULT_MODIFIED_FIELD = "geändert"
# Option B: Wenn du nur den einen Layout aus der .env nutzen willst, kommentiere Zeile 30-35 aus und nutze dies:
# if SINGLE_LAYOUT:
#     LAYOUTS = [SINGLE_LAYOUT]
# else:
#     raise ValueError("Kein Layout in .env gefunden und keine Liste hardcodiert.")

print(f"Verbinde mit Server: {SERVER}")
print(f"Datenbank: {DATABASE}")
print(f"Verarbeite Layouts: {LAYOUTS}\n")

CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# --- HILFSFUNKTIONEN ---

def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

def get_cache_file_path(layout_name):
    safe_name = sanitize_filename(layout_name)
    pattern = f"{safe_name}_*.json"
    files = list(CACHE_DIR.glob(pattern))
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]

def load_existing_cache(layout_name):
    cache_file = get_cache_file_path(layout_name)
    if not cache_file or not cache_file.exists():
        return {"cached_at": None, "last_modified": None, "record_count": 0, "records": []}

    print(f"  -> Lade Cache von: {cache_file.name}")
    with open(cache_file, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_filemaker_timestamp(value):
    if not value: return None
    try:
        return datetime.strptime(value, "%m/%d/%Y %H:%M:%S")
    except ValueError:
        return None

def format_filemaker_timestamp(value):
    if not value: return None
    return value.strftime("%m/%d/%Y %H:%M:%S")

def get_last_modified_from_records(records, layout_name):
    field_name = MODIFIED_FIELDS_MAP.get(layout_name, DEFAULT_MODIFIED_FIELD)
    timestamps = []
    for record in records:
        raw_value = record.get("fieldData", {}).get(field_name)
        if not raw_value: continue
        ts = parse_filemaker_timestamp(raw_value)
        if ts: timestamps.append(ts)
    return max(timestamps) if timestamps else None

# --- API FUNKTIONEN ---

def login():
    base_url = f"{SERVER}/fmi/data/vLatest/databases/{DATABASE}"
    login_url = f"{base_url}/sessions"
    
    try:
        # Debug Ausgabe (optional, später auskommentieren)
        # print(f"Login URL: {login_url}") 
        
        login_response = requests.post(
            login_url,
            auth=HTTPBasicAuth(USER, PASSWORD),
            json={},
            timeout=10
        )
        
        if login_response.status_code != 200:
            print(f"Login fehlgeschlagen: {login_response.status_code}")
            print(f"Antwort: {login_response.text}")
            login_response.raise_for_status()
            
        token = login_response.json()["response"]["token"]
        return base_url, token
    except requests.exceptions.RequestException as e:
        print(f"Verbindungsfehler beim Login: {e}")
        raise

def logout(base_url, token):
    if not token: return
    logout_url = f"{base_url}/sessions/{token}"
    try:
        requests.delete(logout_url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
    except:
        pass

def fetch_all_records(base_url, token, layout):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    all_records = []
    offset = 1
    limit = 1000

    print(f"  Starte VOLLABGLEICH für '{layout}' (kann bei vielen Daten dauern...)")

    while True:
        records_url = f"{base_url}/layouts/{layout}/records?_offset={offset}&_limit={limit}"
        # print(f"  Hole Batch ab Offset {offset}...")

        response = requests.get(records_url, headers=headers, timeout=120)
        
        if response.status_code != 200:
            print(f"  ERROR beim Laden von '{layout}': {response.status_code}")
            print(f"  Antwort: {response.text}")
            response.raise_for_status()

        batch = response.json()["response"].get("data", [])
        if not batch:
            break

        all_records.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    return all_records

def fetch_changed_records(base_url, token, layout, last_modified):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    all_records = []
    offset = 1
    limit = 500
    last_modified_text = format_filemaker_timestamp(last_modified)

    # Welches Feld sollen wir nutzen?
    field_name = MODIFIED_FIELDS_MAP.get(layout, DEFAULT_MODIFIED_FIELD)

    print(f"  Suche nach Änderungen in '{field_name}' seit {last_modified_text}...")

    while True:
        find_url = f"{base_url}/layouts/{layout}/_find"
        payload = {
            "query": [{MODIFIED_FIELD: f">{last_modified_text}"}],
            "limit": limit,
            "offset": offset,
            "sort": [{"fieldName": MODIFIED_FIELD, "sortOrder": "ascend"}]
        }

        response = requests.post(find_url, headers=headers, json=payload, timeout=30)

        # SPEZIFISCHE BEHANDLUNG VON FEHLER 1704 (Kein Support für _find)
        if response.status_code == 500:
            try:
                body = response.json()
                messages = body.get("messages", [])
                code = messages[0].get("code") if messages else ""
                
                if code == "1704":
                    print(f"  ⚠️  FEHLER 1704: Dieses Layout unterstützt keine Suchen (_find).")
                    print(f"     Grund: Layout ist evtl. 'Nur-Ansicht' oder Benutzer hat kein Suchrecht.")
                    print(f"     -> Strategie: Wechsel zu VOLLABGLEICH für dieses Layout.")
                    return None # Signal an main(): Mach Vollabgleich!
                
                elif code == "401":
                    # Keine Datensätze gefunden -> Das ist okay, einfach abbrechen
                    break
                
                else:
                    print(f"  ⚠️  FileMaker Fehler {code}: {messages[0].get('message')}")
                    print(f"     -> Wechsel zu VOLLABGLEICH.")
                    return None

            except Exception as e:
                print(f"  Fehler beim Parsen der Antwort: {e}")
                return None
        
        if response.status_code != 200:
             print(f"  Unerwarteter Fehler {response.status_code}: {response.text}")
             response.raise_for_status()

        batch = response.json()["response"].get("data", [])
        if not batch:
            break

        all_records.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    return all_records

def merge_records(existing_records, changed_records):
    records_by_id = {r["recordId"]: r for r in existing_records}
    for record in changed_records:
        records_by_id[record["recordId"]] = record
    return list(records_by_id.values())

def save_cache(layout_name, records):
    last_modified = get_last_modified_from_records(records, layout_name)
    safe_name = sanitize_filename(layout_name)
    timestamp_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{safe_name}_{timestamp_str}.json"
    filepath = CACHE_DIR / filename

    payload = {
        "cached_at": datetime.now().isoformat(timespec="seconds"),
        "last_modified": format_filemaker_timestamp(last_modified) if last_modified else None,
        "source": {
            "server": SERVER,
            "database": DATABASE,
            "layout": layout_name
        },
        "record_count": len(records),
        "records": records
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"  ✅ Gespeichert: {filename} ({len(records)} Datensätze)")

def archive_old_cache_files():
    """
    Bereinigt den Cache-Ordner:
    1. Erstellt einen Archiv-Ordner 'data/cache/archive'.
    2. Behält pro Layout nur die ALLERNEUESTE Datei im Hauptordner.
    3. Verschiebt alle älteren Dateien ins Archiv.
    """
    if not CACHE_DIR.exists():
        return

    # Archiv-Ordner definieren und erstellen
    archive_dir = CACHE_DIR / "archive"
    archive_dir.mkdir(exist_ok=True)
    
    print("\n📦 Starte Cache-Archivierung...")
    
    files_by_layout = {}
    all_files = list(CACHE_DIR.glob("*.json"))
    
    # Dateien gruppieren
    for file in all_files:
        filename = file.name
        # Ignoriere Dateien, die schon im Archiv sind (sicherheitshalber)
        if file.parent == archive_dir:
            continue
            
        parts = filename.rsplit('_', 1) 
        if len(parts) == 2:
            layout_part = parts[0] 
            if layout_part not in files_by_layout:
                files_by_layout[layout_part] = []
            files_by_layout[layout_part].append(file)
        else:
            if "unknown" not in files_by_layout:
                files_by_layout["unknown"] = []
            files_by_layout["unknown"].append(file)

    moved_count = 0
    kept_count = 0

    for layout_name, files in files_by_layout.items():
        if len(files) <= 1:
            continue # Nur eine Datei, nichts zu tun
        
        # Sortiere nach Änderungsdatum der Datei (neueste zuerst)
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Die erste Datei ist die neueste -> BEHALTEN
        newest = files[0]
        kept_count += 1
        
        # Alle anderen ins Archiv verschieben
        for old_file in files[1:]:
            try:
                # Zielname im Archiv: Behalte den Namen bei, oder füge Zeitstempel hinzu wenn Konflikt
                target_path = archive_dir / old_file.name
                
                # Falls im Archiv schon eine Datei mit gleichem Namen liegt (selten, aber möglich)
                if target_path.exists():
                    timestamp = datetime.now().strftime("%H%M%S")
                    target_path = archive_dir / f"{old_file.stem}_{timestamp}{old_file.suffix}"
                
                old_file.rename(target_path)
                print(f"  📂 Archiviert: {old_file.name} -> archive/")
                moved_count += 1
            except Exception as e:
                print(f"  ⚠️  Konnte {old_file.name} nicht archivieren: {e}")

    if moved_count > 0:
        print(f"✅ Archivierung abgeschlossen: {kept_count} Dateien behalten, {moved_count} Dateien ins Archiv verschoben.")
    else:
        print("✅ Keine alten Dateien zum Archivieren gefunden.")

# --- MAIN ---

if __name__ == "__main__":
    base_url, token = login()
    
    # Globale Variable für records, damit sie immer definiert ist
    records = None 

    try:
        for layout in LAYOUTS:
            print(f"--- Verarbeite Layout: {layout} ---")
            
            cache = load_existing_cache(layout)
            existing_records = cache.get("records", [])
            
            # WICHTIG: Layout-Name an die Funktion übergeben!
            last_modified = get_last_modified_from_records(existing_records, layout)

            if last_modified:
                print(f"  Letztes Update: {format_filemaker_timestamp(last_modified)}")
                
                # Versuch inkrementelles Update
                changed_records = fetch_changed_records(base_url, token, layout, last_modified)
                
                if changed_records is None:
                    # Fall A: Suche fehlgeschlagen (Fehler 1704, 102, etc.) -> Vollabgleich
                    print(f"  -> Inkrementelles Update fehlgeschlagen. Starte VOLLABGLEICH...")
                    try:
                        records = fetch_all_records(base_url, token, layout)
                    except Exception as e:
                        print(f"  ❌ KRITISCHER FEHLER: Vollabgleich für '{layout}' fehlgeschlagen: {e}")
                        print(f"  -> Überspringe dieses Layout, um den Rest zu retten.")
                        continue # Springe zum nächsten Layout
                
                elif len(changed_records) > 0:
                    # Fall B: Änderungen gefunden -> Mergen
                    print(f"  {len(changed_records)} Änderungen gefunden. Mergen...")
                    records = merge_records(existing_records, changed_records)
                
                else:
                    # Fall C: Keine Änderungen -> Bestehende Daten nutzen
                    print("  Keine Änderungen gefunden. Nutze bestehenden Cache.")
                    records = existing_records

            else:
                # Fall D: Kein Cache vorhanden -> Vollabgleich
                print("  Kein Cache gefunden. Starte VOLLABGLEICH...")
                try:
                    records = fetch_all_records(base_url, token, layout)
                except Exception as e:
                    print(f"  ❌ KRITISCHER FEHLER: Vollabgleich für '{layout}' fehlgeschlagen: {e}")
                    continue

            # Sicherheitscheck: Ist records immer noch None?
            if records is None:
                print(f"  ⚠️  Warnung: 'records' ist None für {layout}. Überspringe Speichern.")
                continue

            # Speichern
            save_cache(layout, records)
            print(f"  ✅ Fertig für '{layout}': {len(records)} Datensätze.")
            print("-" * 30)

    except Exception as e:
        print(f"\n❝ ABBRUCH wegen unerwartetem Fehler: {e} ❞")
        import traceback
        traceback.print_exc()
    finally:
        logout(base_url, token)
        archive_old_cache_files()
        print("\nAlle Aufgaben abgeschlossen. Sitzung beendet.")