from components.sidebar import render_sidebar
from utils import apply_filters, load_data, apply_group_mapping
import streamlit as st
import json
from pathlib import Path
import os

import streamlit as st

st.set_page_config(page_title="Open-Library-Zutritte", page_icon="🏛️", layout="wide")
# --- 1. Konfiguration laden ---
CONFIG_PATH = Path("data/config.json")

# Config laden
config = {}
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        # Optional: Zur Kontrolle in der Sidebar anzeigen, ob sie geladen wurde
        # st.sidebar.success("Config geladen") 
    except json.JSONDecodeError as e:
        st.error(f"Fehler beim Lesen der config.json: {e}")
        config = {}
else:
    st.warning(f"Datei {CONFIG_PATH} nicht gefunden. Verwende Standardwerte.")

# Prüfen, ob Daten geladen wurden
if 'data' not in st.session_state or st.session_state['data'] is None:
    st.error("Keine Daten geladen. Bitte starten Sie das Dashboard über die [Startseite](../app.py).")
    st.stop()

data = st.session_state['data']
df_users = data.get("users")
df_ausleihe = data.get("loans") 

if df_users is None:
    st.warning("Keine Nutzerdaten verfügbar.")
    st.stop()


filters = render_sidebar(df_ausleihe, config)

filtered_df = apply_filters(
    df_ausleihe,
    filters["date_range"],
    filters.get("Zweigstelle", []),
    filters.get("Medienart", []),
    filters.get("Benutzergruppe", []),
    filters.get("Kategorie Alter", []),
    nur_erstausleihen=filters["nur_erstausleihen"]
)
