import json
from pathlib import Path
from pprint import pprint

CACHE_FILE = Path("data/cache/filemaker_records.json")

with open(CACHE_FILE, "r", encoding="utf-8") as f:
    cache = json.load(f)

records = cache.get("records", [])

matches = [
    record
    for record in records
    if record.get("fieldData", {}).get("Zweigstelle") == "Bibliothek"
]

print(f"Gefundene Datensätze mit Zweigstelle='Bibliothek': {len(matches)}")

for record in matches[:50]:
    fields = record.get("fieldData", {})

    print({
        "recordId": record.get("recordId"),
        "Ausleihdatum": fields.get("Ausleihdatum"),
        "Rückgabedatum": fields.get("Rückgabedatum"),
        "NR Zugang": fields.get("NR Zugang"),
        "MedienTitel": fields.get("MedienTitel"),
        "Ausleihperson": fields.get("Ausleihperson"),
        "Zweigstelle": fields.get("Zweigstelle"),
        "Transaktion(1)": fields.get("Transaktion(1)"),
        "Transaktion(2)": fields.get("Transaktion(2)"),
        "geändert": fields.get("geändert"),
    })