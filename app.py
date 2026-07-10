import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from dateutil.relativedelta import relativedelta
from utils import load_data, apply_filters, apply_config, load_swiss_locations,validate_and_clean_locations

st.set_page_config(
    page_title="Bibliothek Seengen - Dashboard",
    page_icon="📚",
    layout="wide"
)

st.title("📚 Bibliothek Seengen – Leitungs-Dashboard")
st.caption("Statusüberblick und strategische Kennzahlen")

# --- 1. Konfiguration laden ---
CONFIG_FILE = Path("data/config.json")
if CONFIG_FILE.exists():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
else:
    config = {}

visible_filters = config.get("visible_filters", [])
default_filters = config.get("default_filters", {})

# --- 2. DATEN LADEN (ZENTRAL & EFFIZIENT) ---

# 1. Rohdaten laden, falls nicht vorhanden
if 'data' not in st.session_state or st.session_state['data'] is None:
    with st.spinner('Lade Bibliotheksdaten...'):
        raw_data = load_data()
        st.session_state['data'] = raw_data

# 2. Referenzdaten laden, falls nicht vorhanden
if 'ref_swiss' not in st.session_state or st.session_state['ref_swiss'] is None:
    with st.spinner('Lade Referenzdaten (PLZ/Orte)...'):
        try:
            df_ref = load_swiss_locations("data/swiss_locations.csv")
            st.session_state['ref_swiss'] = df_ref
        except Exception as e:
            st.error(f"Fehler beim Laden der Referenzdaten: {e}")
            st.session_state['ref_swiss'] = None

# 3. Validierung durchführen, falls Daten da sind und noch nicht validiert wurde
# WICHTIG: Wir prüfen hier explizit mit 'is not None' und nicht nur 'if variable'
current_data = st.session_state.get('data')
current_ref = st.session_state.get('ref_swiss')
is_validated = st.session_state.get('users_validated', False)

if current_data is not None and current_ref is not None and not is_validated:
    with st.spinner('Validiere Benutzeradressen (kann einen Moment dauern)...'):
        df_users_raw = current_data.get('users')
        
        # Auch hier explizit prüfen
        if df_users_raw is not None and not df_users_raw.empty:
            try:
                # Die Validierung durchführen
                df_users_validated, _ = validate_and_clean_locations(df_users_raw, current_ref)
                
                # Die validierten Daten ZURÜCK in den session_state speichern
                # Wir überschreiben das 'users' Dict im bestehenden Data-Objekt
                st.session_state['data']['users'] = df_users_validated
                st.session_state['users_validated'] = True
            except Exception as e:
                st.error(f"Fehler bei der Validierung: {e}")
                st.session_state['users_validated'] = True # Verhindert Endlosschleife bei Fehler
        else:
            # Keine Nutzerdaten zum Validieren -> Trotzdem markieren, damit es nicht wieder versucht wird
            st.session_state['users_validated'] = True

# --- 3. DATEN AUS DEM SPEICHER HOLEN ---
# Sicherer Zugriff
if 'data' not in st.session_state or st.session_state['data'] is None:
    st.warning("Daten noch nicht geladen. Bitte Seite neu laden.")
    st.stop()

data = st.session_state['data']
df_ausleihe = data.get("loans")
df_users = data.get("users") # Jetzt validiert

# Prüfen ob Ausleihdaten da sind (explizit)
if df_ausleihe is None or df_ausleihe.empty:
    st.error("Keine Ausleihdaten verfügbar.")
    st.stop()

# --- 4. Config anwenden ---
df_ausleihe = apply_config(df_ausleihe, config)

# --- Sidebar Filter ---
st.sidebar.header("Globale Filter")
st.sidebar.info("Diese Filter gelten für alle Seiten des Dashboards.")

nur_erstausleihen = st.sidebar.checkbox("Nur Erstausleihen", value=False, help="Verlängerungen ausblenden")

today = date.today()
date_range = None
if "Ausleihdatum" in df_ausleihe.columns:
    min_date = df_ausleihe["Ausleihdatum"].min()
    max_date = df_ausleihe["Ausleihdatum"].max()
    if pd.notna(min_date) and pd.notna(max_date):
        min_date = min_date.date()
        max_date = max_date.date()
        years_back = default_filters.get("date_years_back", 2)
        default_start = max(today - relativedelta(years=years_back), min_date)
        date_range = st.sidebar.date_input("Ausleihdatum", value=(default_start, max_date))

def get_dynamic_multiselect(label, column_name):
    if column_name not in visible_filters or column_name not in df_ausleihe.columns:
        return []
    values = sorted([str(v) for v in df_ausleihe[column_name].dropna().unique() if str(v).strip() != ""])
    default = config.get("default_filters", {}).get(column_name, values)
    return st.sidebar.multiselect(label, options=values, default=[v for v in default if v in values])

sel_zweig = get_dynamic_multiselect("Zweigstelle", "Zweigstelle")
sel_medien = get_dynamic_multiselect("Medienart", "Medienart")
sel_gruppe = get_dynamic_multiselect("Benutzergruppe", "Benutzergruppe")
sel_alter = get_dynamic_multiselect("Kategorie Alter", "Kategorie Alter")

filtered_df = apply_filters(df_ausleihe, date_range, sel_zweig, sel_medien, sel_gruppe, sel_alter, nur_erstausleihen)

# --- KPIs ---
st.subheader("Aktuelle Kennzahlen")
total_loans = len(filtered_df)
open_loans = filtered_df["Rückgabedatum"].isna().sum() if "Rückgabedatum" in filtered_df.columns else 0
active_users = filtered_df["Ausleihperson"].nunique() if "Ausleihperson" in filtered_df.columns else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Ausleihen (Filter)", f"{total_loans:,}".replace(",", "'"))
col2.metric("Offene Ausleihen", f"{open_loans:,}".replace(",", "'"))
col3.metric("Aktive Kund:innen", f"{active_users:,}".replace(",", "'"))
col4.metric("Datensatz-Quelle", "FileMaker Cache")

st.divider()

# --- Trend Chart ---
st.subheader("Ausleihtrend (Letzte 12 Monate)")
if "Ausleihdatum" in filtered_df.columns:
    trend = (
        filtered_df.dropna(subset=["Ausleihdatum"])
        .assign(Monat=lambda x: x["Ausleihdatum"].dt.to_period("M").dt.to_timestamp())
        .groupby("Monat")
        .size()
        .reset_index(name="Ausleihen")
        .sort_values("Monat")
    )
    if not trend.empty:
        st.line_chart(trend, x="Monat", y="Ausleihen", width="stretch")
    else:
        st.info("Keine Daten im gewählten Zeitraum.")

st.divider()
st.markdown("""
### Navigation
Nutzen Sie das Menü links, um detaillierte Analysen zu sehen:
- **📊 Ausleihen**: Detaillierte Transaktionsanalysen.
- **👥 Benutzer**: Zielgruppenanalyse, **Datenqualitäts-Check** und Karte.
- **📚 Medien**: Bestandsumlauf und Top-Listen.
- **🔓 OpenLibrary**: Spezifische Analysen zur Selbstbedienung.
- **⚙️ Einstellungen**: Dashboard konfigurieren.
""")

# =========================================================================
# 🛡️ KOMPAKTER DATENQUALITÄTS-HINWEIS (Nur Ampel-Funktion)
# =========================================================================

# Da df_users jetzt schon validiert ist, können wir direkt die Spalten nutzen
if df_users is not None and 'Ort_Match_Status' in df_users.columns:
    STATUS_OK = '✅ OK'
    STATUS_CORRECTED_LIST = ['⚠️ Korrigiert', '⚠️ Ort korrigiert', '⚠️ PLZ korrigiert']
    
    mask_incomplete = (
        df_users['PLZ'].isna() | (df_users['PLZ'].astype(str).str.strip() == '') |
        df_users['Wohnort'].isna() | (df_users['Wohnort'].astype(str).str.strip() == '')
    )
    count_incomplete = mask_incomplete.sum()
    
    df_complete = df_users[~mask_incomplete]
    count_ok = (df_complete['Ort_Match_Status'] == STATUS_OK).sum()
    count_corr = df_complete['Ort_Match_Status'].isin(STATUS_CORRECTED_LIST).sum()
    count_unknown = (df_complete['Ort_Match_Status'] == '❌ Unbekannt').sum()
    
    total = len(df_users)
    good_rate = ((count_ok + count_corr) / total * 100) if total > 0 else 0
    
    st.divider()
    st.subheader("📊 Datenqualitäts-Status (Benutzer)")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Zugeordnete Orte", f"{good_rate:.1f}%")
    c2.metric("Problematische Einträge", f"{count_unknown + count_incomplete:,}")
    
    if count_unknown > 0 or count_incomplete > 0:
        c3.metric("Handlungsbedarf", "Ja", delta_color="inverse")
        st.warning(f"""
        **Achtung:** Es liegen **{count_unknown}** fehlerhafte Orte und **{count_incomplete}** unvollständige Datensätze vor.
        
        👉 **Bitte prüfen Sie die Details auf der Seite [👥 Benutzer](pages/02_Benutzer.py)**, um diese zu bereinigen.
        """)
    else:
        c3.metric("Handlungsbedarf", "Nein", delta_color="off")
        st.success("✅ Alle Benutzerdaten sind vollständig und korrekt zugeordnet.")

# =========================================================================
# Kurzer Hinweis zu anderen Datenqualitäts-Problemen (Optional)
# =========================================================================
# Wenn du auch Medienart/Gruppen-Probleme kurz anzeigen willst:
col_grp_raw = df_users['Benutzergruppe'].astype(str) if df_users is not None else pd.Series()
grp_issues = col_grp_raw.nunique() - col_grp_raw.str.strip().nunique() if len(col_grp_raw) > 0 else 0

if grp_issues > 0:
    st.info(f"ℹ️ Hinweis: Es wurden auch **{grp_issues}** Inkonsistenzen in den Benutzergruppen gefunden (z.B. durch Leerzeichen). Details siehe Seite **👥 Benutzer**.")