import json
import os
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()


SERVER = os.getenv("FILEMAKER_SERVER")
DATABASE = os.getenv("FILEMAKER_DATABASE")
LAYOUT = os.getenv("FILEMAKER_LAYOUT")
USER = os.getenv("FILEMAKER_USER")
PASSWORD = os.getenv("FILEMAKER_PASSWORD")
MODIFIED_FIELD = os.getenv("FILEMAKER_MODIFIED_FIELD", "geändert")

CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_FILE = CACHE_DIR / "filemaker_records.json"


def load_existing_cache():
    if not CACHE_FILE.exists():
        return {
            "cached_at": None,
            "last_modified": None,
            "record_count": 0,
            "records": []
        }

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_filemaker_timestamp(value):
    """
    Erwartetes Format aus deinem Beispiel:
    11/17/2025 12:39:47
    """
    if not value:
        return None

    return datetime.strptime(value, "%m/%d/%Y %H:%M:%S")


def format_filemaker_timestamp(value):
    """
    Gibt den Timestamp wieder im FileMaker-Find-Format zurück.
    """
    return value.strftime("%m/%d/%Y %H:%M:%S")


def get_last_modified_from_records(records):
    timestamps = []

    for record in records:
        raw_value = record.get("fieldData", {}).get(MODIFIED_FIELD)

        if not raw_value:
            continue

        try:
            timestamps.append(parse_filemaker_timestamp(raw_value))
        except ValueError:
            print(f"Konnte Zeitstempel nicht lesen: {raw_value}")

    if not timestamps:
        return None

    return max(timestamps)


def login():
    base_url = f"{SERVER}/fmi/data/vLatest/databases/{DATABASE}"

    login_url = f"{base_url}/sessions"
    login_response = requests.post(
        login_url,
        auth=HTTPBasicAuth(USER, PASSWORD),
        json={}
    )

    print("Login Status:", login_response.status_code)
    login_response.raise_for_status()

    token = login_response.json()["response"]["token"]

    return base_url, token


def logout(base_url, token):
    logout_url = f"{base_url}/sessions/{token}"

    requests.delete(
        logout_url,
        headers={"Authorization": f"Bearer {token}"}
    )


def fetch_all_records(base_url, token):
    """
    Erstbefüllung: holt alle Datensätze paginiert.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    all_records = []
    offset = 1
    limit = 500

    while True:
        records_url = (
            f"{base_url}/layouts/{LAYOUT}/records"
            f"?_offset={offset}&_limit={limit}"
        )

        print(f"Hole alle Datensätze {offset} bis {offset + limit - 1} ...")

        response = requests.get(records_url, headers=headers)
        response.raise_for_status()

        batch = response.json()["response"].get("data", [])

        if not batch:
            break

        all_records.extend(batch)

        print(f"Geladen bisher: {len(all_records)}")

        if len(batch) < limit:
            break

        offset += limit

    return all_records


def fetch_changed_records(base_url, token, last_modified):
    """
    Folgeabruf: holt nur Datensätze, deren Feld 'geändert'
    neuer ist als der letzte gespeicherte Zeitstempel.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    all_records = []
    offset = 1
    limit = 500

    last_modified_text = format_filemaker_timestamp(last_modified)

    while True:
        find_url = f"{base_url}/layouts/{LAYOUT}/_find"

        payload = {
            "query": [
                {
                    MODIFIED_FIELD: f">{last_modified_text}"
                }
            ],
            "limit": limit,
            "offset": offset,
            "sort": [
                {
                    "fieldName": MODIFIED_FIELD,
                    "sortOrder": "ascend"
                }
            ]
        }

        print(
            f"Hole geänderte Datensätze nach {last_modified_text}, "
            f"Offset {offset} ..."
        )

        response = requests.post(find_url, headers=headers, json=payload)

        # FileMaker meldet "keine Datensätze gefunden" oft mit Code 401
        if response.status_code == 500:
            try:
                body = response.json()
                messages = body.get("messages", [])
                if messages and messages[0].get("code") == "401":
                    print("Keine neuen/geänderten Datensätze gefunden.")
                    break
            except Exception:
                pass

        response.raise_for_status()

        batch = response.json()["response"].get("data", [])

        if not batch:
            break

        all_records.extend(batch)

        print(f"Geändert geladen bisher: {len(all_records)}")

        if len(batch) < limit:
            break

        offset += limit

    return all_records


def merge_records(existing_records, changed_records):
    """
    Geänderte Datensätze ersetzen die alte Version.
    Neue Datensätze werden ergänzt.
    Schlüssel ist FileMaker recordId.
    """
    records_by_id = {}

    for record in existing_records:
        records_by_id[record["recordId"]] = record

    for record in changed_records:
        records_by_id[record["recordId"]] = record

    return list(records_by_id.values())


def save_cache(records):
    last_modified = get_last_modified_from_records(records)

    payload = {
        "cached_at": datetime.now().isoformat(timespec="seconds"),
        "last_modified": (
            format_filemaker_timestamp(last_modified)
            if last_modified
            else None
        ),
        "source": {
            "server": SERVER,
            "database": DATABASE,
            "layout": LAYOUT
        },
        "record_count": len(records),
        "records": records
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"{len(records)} Datensätze gespeichert in {CACHE_FILE}")

    if last_modified:
        print(f"Letzter Änderungszeitstempel: {format_filemaker_timestamp(last_modified)}")


if __name__ == "__main__":
    cache = load_existing_cache()
    existing_records = cache.get("records", [])

    print(f"Vorhandene Datensätze im Cache: {len(existing_records)}")

    last_modified = get_last_modified_from_records(existing_records)

    if last_modified:
        print(
            "Letzter Änderungszeitstempel im Cache:",
            format_filemaker_timestamp(last_modified)
        )
    else:
        print("Kein Cache-Zeitstempel gefunden. Es wird ein Vollabgleich gemacht.")

    base_url, token = login()

    try:
        if last_modified:
            changed_records = fetch_changed_records(
                base_url=base_url,
                token=token,
                last_modified=last_modified
            )

            print(f"Neue/geänderte Datensätze: {len(changed_records)}")

            records = merge_records(existing_records, changed_records)

        else:
            records = fetch_all_records(base_url, token)

        save_cache(records)

    finally:
        logout(base_url, token)