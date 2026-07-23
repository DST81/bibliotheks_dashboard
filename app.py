import streamlit as st
import pandas as pd
import json
import altair as alt
from pathlib import Path
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from utils import load_data, apply_filters, apply_config, load_swiss_locations,validate_and_clean_locations
from components.ui import kpi_box
import subprocess
import sys

# ToDo: Stichtag rauslöschen im Live-Betrieb
STICHTAG_VERSCHIEBUNG_TAGE = 30   # Echtbetrieb =0

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
filters_config = config.get('filters', {})
visible_filters = filters_config.get("visible", [])
default_filters = filters_config.get("defaults", {})

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
if 'data' not in st.session_state or st.session_state['data'] is None:
    st.warning("Daten noch nicht geladen. Bitte Seite neu laden.")
    st.stop()
metadata = st.session_state["data"].get("metadata", {})


labels = {
    "loans": "📚 Ausleihen",
    "catalog": "📖 Katalog",
    "users": "👥 Benutzer",
    "smartlibrary": "OpenLibrary" 
}

if metadata:
    zeilen = []

    for key in ["loans", "catalog", "users", "smartlibrary"]:
        info = metadata.get(key)

        if not info:
            continue

        datenstand = "-"
        fetch = "-"

        if info.get("data_date"):
            datenstand = datetime.strptime(
                info["data_date"], "%Y-%m-%d"
            ).strftime("%d.%m.%Y")

        if info.get("cached_at"):
            fetch = datetime.fromisoformat(
                info["cached_at"]
            ).strftime("%d.%m.%Y %H:%M Uhr")

        zeilen.append(
            f"<b>{labels[key]}</b>: "
            f"Import <b>{fetch}</b>"
        )

    st.markdown(f"""
    <div style="
        border:1px solid #E6E6E6;
        border-radius:8px;
        padding:8px 12px;
        background:#fafafa;
        font-size:0.9rem;
        line-height:1.35;
        margin-bottom:10px;
    ">
        <b>🕒Letzte Datenaktualisierung - Datenstand {datenstand}</b><br>
        {' &nbsp;&nbsp;|&nbsp;&nbsp; '.join(zeilen)}
    </div>
    """, unsafe_allow_html=True)

data = st.session_state['data']
df_ausleihe = data.get("loans")
df_users = data.get("users")
data_dates = data.get("dates", {}) # Die Datums-Infos holen

# --- NEU: Zentrale Datenstand-Anzeige ---
# Wir sammeln alle verfügbaren Datenstände in einer Liste
available_dates = []
if data_dates.get("loans"):
    available_dates.append(f"Ausleihen: {data_dates['loans']}")
if data_dates.get("users"):
    available_dates.append(f"Benutzer: {data_dates['users']}")
if data_dates.get("catalog"):
    available_dates.append(f"Katalog: {data_dates['catalog']}")

if available_dates:
    # Joinen der Liste zu einem String
    date_string = " | ".join(available_dates)
    st.caption(f"📅 Datenstand: {date_string}")
    st.divider() # Optional: Ein Trennstrich unter Titel und Datenstand

# Prüfen ob Ausleihdaten da sind (explizit)
if df_ausleihe is None or df_ausleihe.empty:
    st.error("Keine Ausleihdaten verfügbar.")
    st.stop()

# --- 4. Config anwenden ---
df_ausleihe = apply_config(df_ausleihe, config)

# --- Sidebar Filter ---
st.sidebar.header("Globale Filter")
st.sidebar.info("Diese Filter gelten für alle Seiten des Dashboards.")

# Daten aktualisieren
st.sidebar.divider()

if st.sidebar.button(
    "🔄 Daten aktualisieren",
    use_container_width=True,
    help="Lädt alle Daten neu aus dem Bibliothekssystem. Dies dauert einige Minuten."
):

    with st.spinner("⏳ Daten werden aktualisiert... \n\nDies kann 2-5 Minuten dauern"):
        result= subprocess.run(
            [sys.executable, "src/fetch_all_data.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
    if result.returncode==0:
        #Streamlit-Cache leeren
        st.cache_data.clear()
        st.cache_resource.clear()

        #Session-State zurücksetzten
        st.session_state["data"] = None
        st.session_state["users_validated"]=False
        st.session_state["ref_swiss"]=None
        
        st.success("✅ Daten erfolgreich aktualisiert. Dashboard wird neu geladen...")

        st.rerun()

    else:
        st.error("❌ Fehler beim Aktualisieren der Daten.")
        st.code(result.stderr)

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
    default = default_filters.get(column_name, values)
    return st.sidebar.multiselect(label, options=values, default=[v for v in default if v in values])

sel_zweig = get_dynamic_multiselect("Zweigstelle", "Zweigstelle")
sel_medien = get_dynamic_multiselect("Medienart", "Medienart")
sel_gruppe = get_dynamic_multiselect("Benutzergruppe", "Benutzergruppe")
sel_alter = get_dynamic_multiselect("Kategorie Alter", "Kategorie Alter")

filtered_df = apply_filters(
    df_ausleihe,
    date_range,
    sel_zweig,
    sel_medien,
    sel_gruppe,
    sel_alter,
    nur_erstausleihen
)

# Datumsfelder bereinigen
filtered_df["Ausleihdatum"] = pd.to_datetime(
    filtered_df["Ausleihdatum"],
    errors="coerce"
)

filtered_df["Ausleihe bis"] = pd.to_datetime(
    filtered_df["Ausleihe bis"],
    errors="coerce"
)

filtered_df["Rückgabedatum"] = pd.to_datetime(
    filtered_df["Rückgabedatum"],
    errors="coerce"
)

heute = (
    pd.Timestamp.today()
    .normalize()
    - pd.Timedelta(days=STICHTAG_VERSCHIEBUNG_TAGE)
)
aktuelles_jahr = heute.year
vorjahr = aktuelles_jahr - 1

# Aktuelles Jahr und Vorjahr
df_aktuelles_jahr = filtered_df[
    filtered_df["Ausleihdatum"].dt.year == aktuelles_jahr
]

df_vorjahr = filtered_df[
    filtered_df["Ausleihdatum"].dt.year == vorjahr
]

# Offene und überfällige Ausleihen (aktueller Bestand)
offene_medien = filtered_df[
    filtered_df["Rückgabedatum"].isna()
]

ueberfaellig = offene_medien[
    offene_medien["Ausleihe bis"] < heute
].shape[0]

# --- KPIs ---
st.subheader("Aktuelle Kennzahlen")

# Jahreswerte
total_loans = len(df_aktuelles_jahr)
total_loans_old = len(df_vorjahr)

active_users = df_aktuelles_jahr["Ausleihperson"].nunique()
active_users_old = df_vorjahr["Ausleihperson"].nunique()

# Bestandswerte
open_loans = len(offene_medien)

# Eintrittsdatum bereinigen
df_users["Eintritt"] = pd.to_datetime(
    df_users["Eintritt"].replace("", pd.NA),
    format="%m/%d/%Y",
    errors="coerce"
)


# Neue Kund:innen aktuelles Jahr
df_new = df_users[
    df_users["Eintritt"].dt.year == aktuelles_jahr
]

df_new_old = df_users[
    df_users["Eintritt"].dt.year == vorjahr
]
# Alle Benutzer nach Benutzergruppe (Gesamtbestand)
gruppen_total= (
    df_users['Benutzergruppe']
    .fillna('Unbekannt')
    .value_counts()
)
# Mitgliederbestand nach Benutzergruppe
gruppen_aktiv= (
    df_users[df_users["aktiv_passiv"].str.lower()=="aktiv"]
    ["Benutzergruppe"]
    .fillna('Unbekannt')
    .value_counts()
)
new_users = len(df_new)
new_users_old = len(df_new_old)

# Benutzergruppen zählen
gruppen_aktuell = (
    df_new["Benutzergruppe"]
    .fillna("Unbekannt")
    .value_counts()
)

gruppen_vorjahr = (
    df_new_old["Benutzergruppe"]
    .fillna("Unbekannt")
    .value_counts()
)

# Top 5 Gruppen
top_gruppen = gruppen_aktuell.head(5).index

gruppen_anzeige = []

for gruppe in top_gruppen:
    gruppen_anzeige.append(
        f"{gruppe}: <b>{gruppen_aktuell.get(gruppe,0)}</b> "
        f"(Vorjahr: {gruppen_vorjahr.get(gruppe,0)})"
    )

# Rest zusammenfassen
rest_aktuell = gruppen_aktuell.drop(top_gruppen).sum()
rest_vorjahr = gruppen_vorjahr.drop(top_gruppen, errors="ignore").sum()

if rest_aktuell > 0 or rest_vorjahr > 0:
    gruppen_anzeige.append(
        f"Weitere: <b>{rest_aktuell}</b> "
        f"(Vorjahr: {rest_vorjahr})"
    )

gruppen_text = "<br>".join(gruppen_anzeige)

# Gesamt Vorjahr ergänzen
gruppen_text += (
    f"<br><br><b>Gesamt Vorjahr: {new_users_old}</b>"
)


col1, col2, col3, col4 = st.columns(4)

with col1:
    kpi_box(
        "📚 Ausleihen",
        total_loans,
        total_loans_old
    )

with col2:
    kpi_box(
        "🔓 Offene Ausleihen",
        open_loans,
        f"Überfällig: {ueberfaellig}"
    )

with col3:
    kpi_box(
        "👥 Aktive Kund:innen",
        active_users,
        active_users_old
    )

with col4:
    kpi_box(
        "🆕 Neue Kund:innen",
        new_users,
        new_users_old
    )
st.markdown("<br>", unsafe_allow_html=True)

# Ausrichtung über Spaltenlayout
links, mitte, rechts = st.columns([1, 1, 2])

with rechts:
    with st.expander("🆕 Details Neue Kund:innen nach Benutzergruppe"):

        alle_gruppen = (
            pd.DataFrame({
                "Total": gruppen_total,
                "Aktive Benutzer": gruppen_aktiv,
                "Aktuelles Jahr": gruppen_aktuell,
                "Vorjahr": gruppen_vorjahr
            })
            .fillna(0)
            .astype(int)
        )

        alle_gruppen["Veränderung"] = (
            alle_gruppen["Aktuelles Jahr"] -
            alle_gruppen["Vorjahr"]
        )

        def farbe_veraenderung(val):
            if val > 0:
                return "color: green; font-weight: bold;"
            elif val < 0:
                return "color: red; font-weight: bold;"
            else:
                return "color: grey;"


        styled_table = (
            alle_gruppen
            .sort_values(
                "Aktuelles Jahr",
                ascending=False
            )
            .style
            .map(
                farbe_veraenderung,
                subset=["Veränderung"]
            )
        )
        alle_gruppen = alle_gruppen.reset_index()
        alle_gruppen = alle_gruppen.rename(
            columns={"index": "Benutzergruppe"}
        )  

        st.dataframe(
            styled_table,
            width=700,
            column_config={
                "Benutzergruppe": st.column_config.TextColumn(
                    width="medium"
                ),
                "Aktuelles Jahr": st.column_config.NumberColumn(
                    width="small"
                ),
                "Vorjahr": st.column_config.NumberColumn(
                    width="small"
                ),
                "Veränderung": st.column_config.NumberColumn(
                    width="small"
                )
            }
    )
st.divider()
# Ausleihkanal bestimmen
def ermittle_kanal(x):
    if str(x).startswith("App"):
        return "App"
    return "Theke"


if "Transaktion(1)" in df_ausleihe.columns:
    df_ausleihe["Ausleihkanal"] = (
        df_ausleihe["Transaktion(1)"]
        .apply(ermittle_kanal)
    )
else:
    df_ausleihe["Ausleihkanal"] = "Theke"
# --- Trend Chart ---
st.subheader("📈 Ausleihtrend (letzte 12 Monate)")

if "Ausleihdatum" in df_ausleihe.columns:

    df_trend = apply_filters(
        df_ausleihe,
        None,
        sel_zweig,
        sel_medien,
        sel_gruppe,
        sel_alter,
        nur_erstausleihen
    )

    df_trend = df_trend.dropna(subset=["Ausleihdatum"]).copy()

    if not df_trend.empty:
        # Immer die letzten 12 Monate ab heute anzeigen
        heute = pd.Timestamp.today().normalize()
        start_datum = (heute - relativedelta(months=11)).replace(day=1)

        df_trend = df_trend[
            (df_trend["Ausleihdatum"] >= start_datum) &
            (df_trend["Ausleihdatum"] <= heute)
        ]

        trend = (
            df_trend
            .assign(
                Monat=lambda x: x["Ausleihdatum"]
                .dt.to_period("M")
                .dt.to_timestamp()
            )
            .groupby(
                [
                    "Monat",
                    "Ausleihkanal"
                ]
            )
            .size()
            .reset_index(name="Ausleihen")
        )

        # Alle 12 Monate erzeugen (inkl. Monate ohne Ausleihen)
        alle_monate = pd.date_range(
            start=start_datum,
            end=heute,
            freq="MS"
        )

        # Monate + Kanäle vollständig machen
        kanale = ["Theke", "App"]

        vollstaendig = pd.MultiIndex.from_product(
            [
                alle_monate,
                kanale
            ],
            names=[
                "Monat",
                "Ausleihkanal"
            ]
        )

        trend = (
            trend
            .set_index(
                [
                    "Monat",
                    "Ausleihkanal"
                ]
            )
            .reindex(
                vollstaendig,
                fill_value=0
            )
            .reset_index()
        )

        trend["Monat_Label"] = trend["Monat"].dt.strftime("%b %Y")

        chart = (
            alt.Chart(trend)
            .mark_bar()
            .encode(
                x=alt.X(
                    "Monat_Label:N",
                    title="Monat",
                    sort=trend["Monat_Label"].unique().tolist(),
                    axis=alt.Axis(
                        labelAngle=-45
                    )
                ),
                y=alt.Y(
                    "Ausleihen:Q",
                    title="Anzahl Ausleihen"
                ),
                color=alt.Color(
                    "Ausleihkanal:N",
                    title="Kanal",
                    scale=alt.Scale(
                        domain=[
                            "Theke",
                            "App"
                        ],
                        range=[
                            "#4C78A8",
                            "#F58518"
                        ]
                    )
                ),
                tooltip=[
                    alt.Tooltip(
                        "Monat_Label:N",
                        title="Monat"
                    ),
                    alt.Tooltip(
                        "Ausleihkanal:N",
                        title="Kanal"
                    ),
                    alt.Tooltip(
                        "Ausleihen:Q",
                        title="Ausleihen"
                    )
                ]
            )
            .properties(
                height=350
            )
        )

        st.altair_chart(chart, use_container_width=True)

    else:
        st.info("Keine Daten vorhanden.")

app_quote = (
    df_trend["Ausleihkanal"]
    .eq("App")
    .mean()
    * 100
)

st.metric(
    "📱 App-Anteil",
    f"{app_quote:.1f}%"
)
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