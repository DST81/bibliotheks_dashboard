import streamlit as st
import json
import pandas as pd
from pathlib import Path
from utils import load_data

st.set_page_config(page_title="Einstellungen", page_icon="⚙️", layout="wide")
st.title("⚙️ Dashboard Einstellungen & Daten-Mapping")

st.markdown("""
Hier können Sie das Dashboard an die spezifischen Bedürfnisse Ihrer Bibliothek anpassen.
Die Einstellungen werden lokal in einer `config.json` gespeichert und beim nächsten Laden automatisch angewendet.
""")

CONFIG_FILE = Path("data/config.json")

# --- 1. Konfiguration laden oder Standard erstellen ---
default_config = {
    "filters": {
        "visible": ["Zweigstelle", "Medienart", "Benutzergruppe", "Kategorie Alter"],
        "defaults": {}
    },
    "group_mapping": {},
    "custom_replacements": {}
}

# Laden wenn vorhanden
if CONFIG_FILE.exists():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        st.error(f"Fehler beim Lesen der Config: {e}")
        config = default_config
else:
    config = default_config

# sicherstellen, dass Struktur existiert
config.setdefault("filters", {})
config["filters"].setdefault("visible", default_config["filters"]["visible"])
config["filters"].setdefault("defaults", {})
config.setdefault("group_mapping", {})
config.setdefault("custom_replacements", {})

st.divider()

# Prüfen, ob Daten geladen wurden
if 'data' not in st.session_state or st.session_state['data'] is None:
    st.error("Keine Daten geladen. Bitte starten Sie das Dashboard über die [Startseite](../app.py).")
    st.stop()

data = st.session_state['data']
df_users = data.get("users")
df_ausleihe = data.get("loans") 
df_katalog = data.get('catalog')

if df_users is None:
    st.warning("Keine Nutzerdaten verfügbar.")
    st.stop()
available_groups = []
all_columns = []

if df_ausleihe is not None and not df_ausleihe.empty:
    if "Benutzergruppe" in df_ausleihe.columns:
        available_groups = sorted(df_ausleihe["Benutzergruppe"].dropna().unique().astype(str).tolist())
    # Spalten mit wenigen einzigartigen Werten eignen sich gut als Filter
    all_columns = [col for col in df_ausleihe.columns if df_ausleihe[col].nunique() < 50 and col not in ["Ausleihdatum", "Rückgabedatum", "recordId", "modId"]]

# --- 2. Benutzergruppen zusammenfassen (Mapping) ---
st.subheader("1. Benutzergruppen zusammenfassen")
st.info("Fassen Sie mehrere technische Gruppen zu einer logischen Gruppe zusammen. Änderungen werden sofort gespeichert.")

col_input, col_action, col_list = st.columns([2, 1, 3])

with col_input:
    new_group_name = st.text_input("Name der neuen Sammelgruppe", placeholder="z.B. Kinder & Jugendliche", key="input_name")
    source_groups = st.multiselect(
        "Quell-Gruppen auswählen",
        options=available_groups,
        help="Halten Sie Strg/Cmd gedrückt, um mehrere zu wählen.",
        key="input_sources"
    )

with col_action:
    st.write("")
    st.write("")
    # WICHTIG: Wir speichern hier sofort!
    if st.button("➕ Hinzufügen", type="primary", use_container_width=True):
        if not new_group_name or not source_groups:
            st.error("Bitte Name und Gruppen auswählen.")
        elif new_group_name in config["group_mapping"]:
            st.warning(f"Gruppe '{new_group_name}' existiert bereits.")
        else:
            # 1. Zur Variable hinzufügen
            config["group_mapping"][new_group_name] = source_groups
            
            # 2. SOFORT in die Datei schreiben (Auto-Save)
            try:
                CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                
                st.success(f"✅ Gruppe '{new_group_name}' erstellt und gespeichert!")
                st.rerun() # Neu laden, damit die Liste und die Variable aktualisiert werden
            except Exception as e:
                st.error(f"❌ Fehler beim Speichern: {e}")

with col_list:
    st.write("**Aktive Mapping-Regeln:**")
    if config["group_mapping"]:
        for name, sources in config["group_mapping"].items():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{name}**")
                c1.caption(f"Enthält: {', '.join(sources)}")
                # Auch beim Löschen sofort speichern
                if c2.button("Löschen", key=f"del_{name}", use_container_width=True):
                    del config["group_mapping"][name]
                    try:
                        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                            json.dump(config, f, ensure_ascii=False, indent=2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fehler beim Löschen: {e}")
    else:
        st.caption("Keine Regeln definiert.")

st.divider()

# --- 3. Sichtbare Filter auswählen ---
st.subheader("2. Sichtbare Filter konfigurieren")

if all_columns:
    selected_filters = st.multiselect(
        "Aktive Filter-Spalten",
        options=all_columns,
        default=[
            f for f in config["filters"]["visible"]
            if f in all_columns
        ],
        help="Diese Spalten erscheinen in der Sidebar."
    )

    config["filters"]["visible"] = selected_filters
else:
    st.warning("Keine geeigneten Filter-Spalten gefunden.")

st.divider()

st.subheader("💾 Abschluss")
col_save, col_preview = st.columns([1, 2])

with col_save:
    if st.button("Einstellungen speichern & Dashboard neu laden", type="primary", use_container_width=True):
        try:
            # 1. Sicherstellen, dass der Ordner existiert (falls config.json noch nie da war)
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # 2. Schreiben der Datei
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            # 3. Erfolgsmeldung und Neuladen
            st.balloons()
            st.success("✅ Gespeichert! Das Dashboard wird neu geladen...")
            st.rerun() # <--- Wichtig: Erzwingt den Neustart des Skripts
            
        except PermissionError:
            st.error("❌ Zugriff verweigert! Ist die config.json gerade in einem anderen Programm geöffnet oder blockiert durch OneDrive?")
        except Exception as e:
            st.error(f"❌ Fehler beim Speichern: {e}")
            st.info("Tipp: Prüfe, ob der Ordner schreibgeschützt ist.")

with col_preview:
    with st.expander("Vorschau der config.json"):
        st.json(config)

st.caption("Hinweis: Änderungen am Mapping werden erst wirksam, nachdem Sie auf 'Speichern' geklickt haben und das Dashboard neu geladen wurde.")