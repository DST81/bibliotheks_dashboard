import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from dotenv import load_dotenv
from datetime import date, datetime, time
from dateutil.relativedelta import relativedelta
from src.utils import load_data, load_swiss_locations, validate_and_clean_locations, get_library_context
from src.filters import get_sidebar_filters, build_filtered_data
from src.pdf_report import build_report_pdf
from src.report_helpers import build_home_filter_summary, format_pdf_delta
from src.theme import (
    SUCCESS,
    DANGER,
    MUTED,
    COLOR_LOANS,
    COLOR_APP,
    COLOR_RETURNS,
    COLOR_VISITS,
    COLOR_COMPARE_A,
    COLOR_PREVIOUS,
)
from components.icons import BUCH, DASHBOARD, PDF, DATENAKTUALISIERUNG, BESTAND, ANTIQUARIAT, USER, OPEN, EINSTELLUNGEN
from components.ui import kpi_box, title_with_icon
import subprocess
import sys
import os
import re
from pathlib import Path

load_dotenv()
# ToDo: Stichtag rauslöschen im Live-Betrieb
STICHTAG_VERSCHIEBUNG_TAGE = 30   # Echtbetrieb =0
library_context = get_library_context()
BIBLIOTHEK = library_context["library_name"]

def _get_cached_library_logo(cache_dir):
    cache_dir = Path(cache_dir)
    for pattern in ["library_logo.png", "library_logo.jpg", "library_logo.jpeg", "library_logo.webp", "library_logo.gif"]:
        logo_path = cache_dir / pattern
        if logo_path.exists():
            return logo_path
    return None

st.set_page_config(
    page_title=f"Bibliothek {BIBLIOTHEK} - Dashboard",
    page_icon="assets/buch.svg",
    layout="wide"
)

col1, col2 = st.columns([3,2])
with col1:
    title_with_icon(f"Dashboard {BIBLIOTHEK}", BUCH)
    st.caption("Statusüberblick und strategische Kennzahlen")

with col2:
    logo_placeholder = st.empty()

# Daten aktualisieren
st.sidebar.subheader("Daten neuladen")
if st.sidebar.button(
    "Daten aktualisieren",
    use_container_width=True,
    help="Laedt alle Daten neu aus dem Bibliothekssystem. Dies dauert einige Minuten."
):

    with st.spinner("Daten werden aktualisiert... \n\nDies kann 5-10 Minuten dauern"):
        fetch_env = os.environ.copy()
        fetch_env["DASHBOARD_LIBRARY_ID"] = library_context["library_id"]
        fetch_env["DASHBOARD_CACHE_DIR"] = str(library_context["cache_dir"])
        result = subprocess.run(
            [sys.executable, "scripts/fetch_all_data.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=fetch_env
        )
    if result.returncode == 0:
        # Streamlit-Cache leeren
        st.cache_data.clear()
        st.cache_resource.clear()

        # Session-State zuruecksetzen
        st.session_state["data"] = None
        st.session_state["users_validated"] = False
        st.session_state["ref_swiss"] = None

        st.success("Daten erfolgreich aktualisiert. Dashboard wird neu geladen...")

        st.rerun()

    else:
        st.error("Fehler beim Aktualisieren der Daten.")
        st.code(result.stderr)
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
    "antiquariat": "🏷️ Antiquariat",
    "users": "👥 Benutzer",
    "smartlibrary": "🔓 OpenLibrary",
    "preferences": "⚙️ Voreinstellungen",
}

if metadata:
    details = []

    status_labels = {
        "missing": "fehlt",
        "empty": "leer",
        "error": "Fehler",
    }

    for key in [
        "loans",
        "catalog",
        "antiquariat",
        "users",
        "smartlibrary",
        "preferences"
    ]:
        info = metadata.get(key)

        if not info:
            continue

        datenstand = "-"
        fetch = "-"
        status = info.get("status", "loaded")

        if info.get("data_date"):
            datenstand = datetime.strptime(
                info["data_date"], "%Y-%m-%d"
            ).strftime("%d.%m.%Y")

        if info.get("cached_at"):
            fetch = datetime.fromisoformat(
                info["cached_at"]
            ).strftime("%d.%m.%Y %H:%M Uhr")

        details.append({
            "Datenquelle": labels[key],
            "Status": "✓ geladen" if status == "loaded"
                      else status_labels.get(status, status),
            "Import": fetch if status == "loaded" else "-",
        })

    with col2:
        # Detailinformationen
        with st.expander(f"🕒 Letzte Datenaktualisierung · Datenstand {datenstand}"):  
            st.dataframe(
                pd.DataFrame(details),
                hide_index=True,
                use_container_width=True,
            )

data = st.session_state['data']
df_ausleihe = data.get("loans")
df_users = data.get("users")
df_smartlibrary = data.get("smartlibrary", pd.DataFrame())
df_preferences = data.get("preferences", pd.DataFrame())
data_dates = data.get("dates", {}) # Die Datums-Infos holen

logo_path = _get_cached_library_logo(library_context["cache_dir"])
if logo_path:
    with logo_placeholder.container():
        logo_spacer, logo_col = st.columns([1, 0.85])
        with logo_col:
            st.image(str(logo_path), width=300)

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
    #st.divider() # Optional: Ein Trennstrich unter Titel und Datenstand

# Prüfen ob Ausleihdaten da sind (explizit)
if df_ausleihe is None or df_ausleihe.empty:
    st.error("Keine Ausleihdaten verfügbar.")
    st.stop()

# --- Sidebar Filter ---
# st.sidebar.header("Globale Filter")
# st.sidebar.info("Diese Filter gelten für alle Seiten des Dashboards.")


st.sidebar.divider()

filtered_users, filtered_loans, filter_state = get_sidebar_filters(
    df_users=data["users"],
    df_extra=df_ausleihe,
    prefix="global",

    enable_date_filter=True,
    enable_first_loan_toggle=True,

    extra_filters_config=[
        {
            "col": "Zweigstelle_loan",
            "label": "Zweigstelle"
        },
        {
            "col": "Medienart_loan",
            "label": "Medienart"
        },
        {
            "col": "Kategorie Alter_loan",
            "label": "Kategorie Alter"
        }
    ]
)

filtered = build_filtered_data(
    st.session_state["data"],
    filtered_users,
    filtered_loans,
    filter_state
)
filtered_df = filtered["loans"]
filtered_df_no_date = filtered["loans_no_date"].copy()
# Datumsfelder bereinigen
for df_dates in [filtered_df, filtered_df_no_date]:
    df_dates["Ausleihdatum"] = pd.to_datetime(
        df_dates["Ausleihdatum"],
        errors="coerce"
    )

    df_dates["Ausleihe bis"] = pd.to_datetime(
        df_dates["Ausleihe bis"],
        errors="coerce"
    )

    df_dates["Rückgabedatum"] = pd.to_datetime(
        df_dates["Rückgabedatum"],
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
df_aktuelles_jahr = filtered_df_no_date[
    filtered_df_no_date["Ausleihdatum"].dt.year == aktuelles_jahr
]

df_vorjahr = filtered_df_no_date[
    filtered_df_no_date["Ausleihdatum"].dt.year == vorjahr
]

# Offene und überfällige Ausleihen (aktueller Bestand)
offene_medien = filtered_df_no_date[
    filtered_df_no_date["Rückgabedatum"].isna()
]

# Offene Ausleihen nach Medienart
offene_medienart = (
    offene_medien
    .groupby("Medienart_catalog")
    .size()
    .rename("Offen")
    .to_frame()
)

offene_medienart["Überfällig"] = (
    offene_medien[offene_medien["Ausleihe bis"] < heute]
    .groupby("Medienart_catalog")
    .size()
)

offene_medienart = offene_medienart.fillna(0)

offene_medienart["Offen"] = offene_medienart["Offen"].astype(int)
offene_medienart["Überfällig"] = offene_medienart["Überfällig"].astype(int)

offene_medienart["Anteil"] = (
    offene_medienart["Offen"]
    / offene_medienart["Offen"].sum()
    * 100
).round(1)

offene_medienart = (
    offene_medienart
    .sort_values("Offen", ascending=False)
    .reset_index()
    .rename(columns={"Medienart_catalog": "Medienart"})
)
# Offene Ausleihen nach Standort
offene_standort = (
    offene_medien['Standort(1)']
    .fillna('Unbekannt')
    .value_counts()
    .rename_axis('Standort')
    .reset_index(name='Offen')
)
offene_standort['Anteil'] = (
    offene_standort['Offen']
    /offene_standort['Offen'].sum()
    *100
).round(1)

ueberfaellig = offene_medien[
    offene_medien["Ausleihe bis"] < heute
].shape[0]

# --- KPIs ---
st.subheader(f"Kennzahlen {aktuelles_jahr}")

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
        subtext=f"Überfällig: {ueberfaellig}"
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
links, rechts = st.columns([1, 1])

with links:
    with st.expander("🔓 Details offene Ausleihen"):
        tab1, tab2 = st.tabs(
            [
                "Medienarten",
                "Standorte"
            ]
        )
        with tab1:
            st.dataframe(
                offene_medienart,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Offen": st.column_config.NumberColumn(
                        "Anzahl",
                        format="%d"
                    ),
                    "Überfällig": st.column_config.NumberColumn("Überfällig"),
                    "Anteil": st.column_config.NumberColumn(
                        "Anteil",
                        format="%.1f %%"
                    )
                }
            )
        with tab2:
            st.dataframe(
                offene_standort,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Offen": st.column_config.NumberColumn(
                        "Anzahl",
                        format="%d"
                    ),
                    "Anteil": st.column_config.NumberColumn(
                        "Anteil",
                        format="%.1f %%"
                    )
                }
            )

with rechts:
    with st.expander("🆕 Details Kund:innen nach Benutzergruppe"):

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
                return f"color: {SUCCESS}; font-weight: bold;"
            elif val < 0:
                return f"color: {DANGER}; font-weight: bold;"
            else:
                return f"color: {MUTED};"


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



def _norm_text(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _parse_time_value(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"(\d{1,2})[:.](\d{2})", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    match = re.search(r"\b(\d{1,2})\b", text)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return hour, 0
    return None


def _find_branch_col(df):
    for col in df.columns:
        name = _norm_text(col)
        if name in {"zweigstelle", "filiale", "standort", "bibliothek"}:
            return col
    return None


def _filter_smartlibrary_visits(df_smart, df_users_filtered):
    smart = df_smart.copy() if df_smart is not None else pd.DataFrame()
    if smart.empty:
        return smart

    if "Nummer" in smart.columns:
        smart["Nummer"] = (
            smart["Nummer"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    if (
        "Nummer" in smart.columns
        and df_users_filtered is not None
        and "Nummer" in df_users_filtered.columns
    ):
        active_users = (
            df_users_filtered["Nummer"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
        )
        smart = smart[smart["Nummer"].isin(active_users)]

    return smart



def _parse_opening_time(text):
    match = re.search(r"(\d{1,2})[.:](\d{2})", str(text or ""))
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def _parse_staffed_openings(opening_text):
    weekday_map = {
        "mo": 0,
        "montag": 0,
        "di": 1,
        "dienstag": 1,
        "mi": 2,
        "mittwoch": 2,
        "do": 3,
        "donnerstag": 3,
        "fr": 4,
        "freitag": 4,
        "sa": 5,
        "samstag": 5,
        "so": 6,
        "sonntag": 6,
    }
    openings = {idx: [] for idx in range(7)}
    for raw_line in str(opening_text or "").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        day_match = re.match(r"^([A-Za-z??????]{2,10})\b", line)
        if not day_match:
            continue
        day_key = _norm_text(day_match.group(1))
        if day_key not in weekday_map:
            continue
        times = re.findall(r"(\d{1,2}[.:]\d{2})", line)
        if len(times) < 2:
            continue
        close_time = _parse_opening_time(times[-1])
        if close_time:
            openings[weekday_map[day_key]].append(close_time)
    return openings


def _preference_branch_openings(preferences, branch):
    if preferences is None or preferences.empty:
        return None, None, None

    row = preferences.iloc[0]
    branch_key = str(branch or "").strip().lower()
    fallback = None

    for idx in range(1, 10):
        branch_col = f"Zweigstellen({idx})"
        opening_col = f"Oeffnungszeiten 0({idx})"
        opening_text = row.get(opening_col)
        if not str(opening_text or "").strip():
            continue
        fallback = fallback or (opening_text, opening_col, row.get(branch_col, ""))
        configured_branch = str(row.get(branch_col, "")).strip().lower()
        if configured_branch and configured_branch == branch_key:
            return opening_text, opening_col, configured_branch

    if fallback:
        return fallback
    return None, None, None


def _last_staffed_opening(preferences, branch, now):
    opening_text, opening_col, _ = _preference_branch_openings(preferences, branch)
    if not opening_text:
        return None, None

    openings = _parse_staffed_openings(opening_text)
    for days_back in range(0, 21):
        candidate_date = (now - pd.Timedelta(days=days_back)).normalize()
        weekday = int(candidate_date.weekday())
        close_times = sorted(openings.get(weekday, []), reverse=True)
        for hour, minute in close_times:
            candidate_dt = candidate_date + pd.Timedelta(hours=hour, minutes=minute)
            if candidate_dt < now:
                return candidate_dt, opening_col

    return None, opening_col



def _find_return_timestamp(returns, return_dates):
    change_candidates = [
        "geändert",
        "geändert_loan",
        "geaendert",
        "geaendert_loan",
        "Geändert",
        "Geändert_loan",
    ]
    for col in change_candidates:
        if col not in returns.columns:
            continue
        changed = pd.to_datetime(returns[col], errors="coerce")
        same_day = (
            changed.notna()
            & return_dates.notna()
            & changed.dt.date.eq(return_dates.dt.date)
        )
        if same_day.any():
            timestamp = return_dates.copy()
            timestamp.loc[same_day] = changed.loc[same_day]
            return timestamp, col

    return return_dates, None


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

home_extra_kpis = {}
home_openlibrary_kpis = {}

# =====================================================
# Ausleihtrend aktuelles Jahr
# =====================================================

title_with_icon(f"Ausleihtrend {aktuelles_jahr}",DASHBOARD, icon_size=34, level="subheader")


home_trend_chart = None

if "Ausleihdatum" in df_ausleihe.columns:

    heute = pd.Timestamp.today().normalize()
    aktuelles_jahr = heute.year
    vorjahr = aktuelles_jahr - 1

    monate = range(1, 13)
    monate_label = [
        "Jan", "Feb", "Mär", "Apr",
        "Mai", "Jun", "Jul", "Aug",
        "Sep", "Okt", "Nov", "Dez"
    ]

    # --------------------------------------------------
    # Basis-Daten: beide Jahre, mit Ausleihkanal
    # (einmalig berechnet, statt getrennt für aktuell/Vorjahr)
    # --------------------------------------------------

    df_beide = filtered["loans_no_date"].copy()

    if "Ausleihkanal" not in df_beide.columns:
        if "Transaktion(1)" in df_beide.columns:
            df_beide["Ausleihkanal"] = (
                df_beide["Transaktion(1)"]
                .apply(ermittle_kanal)
            )
        else:
            df_beide["Ausleihkanal"] = "Theke"

    df_beide = df_beide.dropna(subset=["Ausleihdatum"]).copy()

    df_beide = df_beide[
        df_beide["Ausleihdatum"].dt.year.isin([vorjahr, aktuelles_jahr])
    ].copy()

    df_beide["Jahr"] = df_beide["Ausleihdatum"].dt.year
    df_beide["Monat"] = df_beide["Ausleihdatum"].dt.month

    stichtag_vorjahr = heute - pd.DateOffset(years=1)

    # Für die KPIs unten: aktuelles Jahr bis heute bzw. verfügbare Daten.
    df_trend = df_beide[
        (df_beide["Jahr"] == aktuelles_jahr)
        & (df_beide["Ausleihdatum"] <= heute)
    ].copy()

    # --------------------------------------------------
    # Monatswerte nach Kanal, für BEIDE Jahre
    # --------------------------------------------------

    bars_beide = (
        df_beide
        .groupby(["Jahr", "Monat", "Ausleihkanal"])
        .size()
        .reset_index(name="Ausleihen")
    )

    idx = pd.MultiIndex.from_product(
        [[vorjahr, aktuelles_jahr], monate, ["Theke", "App"]],
        names=["Jahr", "Monat", "Ausleihkanal"]
    )

    bars_beide = (
        bars_beide
        .set_index(["Jahr", "Monat", "Ausleihkanal"])
        .reindex(idx, fill_value=0)
        .reset_index()
    )

    bars_beide["Monat_Label"] = [
        monate_label[m-1]
        for m in bars_beide["Monat"]
    ]
    bars_beide = bars_beide.rename(columns={"Ausleihkanal": "Kanal"})

    # Aktuelles Jahr: keine zukünftigen Monate anzeigen
    bars = bars_beide[
        (bars_beide["Jahr"] == aktuelles_jahr)
        & (bars_beide["Monat"] <= heute.month)
    ].copy()
    bars["Zeitraum"] = "Aktuell"

    bars_vorjahr = bars_beide[bars_beide["Jahr"] == vorjahr].copy()
    bars_vorjahr["Zeitraum"] = "Vorjahr"

    # --------------------------------------------------
    # Monatsgesamt + kumuliert (Vorjahr + aktuelles Jahr)
    # --------------------------------------------------

    line = (
        df_beide
        .groupby(["Jahr", "Monat"])
        .size()
        .reset_index(name="Ausleihen")
    )
    idx = pd.MultiIndex.from_product(
        [[vorjahr, aktuelles_jahr], range(1, 13)],
        names=["Jahr", "Monat"]
    )

    line = (
        line
        .set_index(["Jahr", "Monat"])
        .reindex(idx, fill_value=0)
        .reset_index()
    )
    line["Monat_Label"] = [
        monate_label[m-1]
        for m in line["Monat"]
    ]

    line["Kumuliert"] = (
        line
        .groupby("Jahr")["Ausleihen"]
        .cumsum()
    )

    line["Linie"] = line["Jahr"].map({
        vorjahr: "Vorjahr",
        aktuelles_jahr: "Aktuelles Jahr"
    })

    vergleich = (
        line.pivot(
            index = "Monat",
            columns = "Jahr",
            values = "Kumuliert"
        )
        .fillna(0)
        .reset_index()
    )
    vergleich.columns = [
        "Monat",
        f"Kumuliert_{vorjahr}",
        f"Kumuliert_{aktuelles_jahr}"
    ]

    vergleich["Differenz"] = (
        vergleich[f"Kumuliert_{aktuelles_jahr}"] -
        vergleich[f"Kumuliert_{vorjahr}"]
    )
    vergleich["Differenz_%"] = (
        vergleich["Differenz"]/
        vergleich[f"Kumuliert_{vorjahr}"]
        .replace(0,np.nan)
        *100
    )

    line = line.merge(
        vergleich,
        on="Monat",
        how="left"
    )

    # NEU: Linie fürs aktuelle Jahr nur bis zum aktuellen Monat zeichnen,
    # damit sie nicht künstlich flach bis Dezember weiterläuft
    line = line[
        (line["Jahr"] != aktuelles_jahr) | (line["Monat"] <= heute.month)
    ].copy()

    # --------------------------------------------------
    # Balken aktuelles Jahr (gestapelt: Theke + App)
    # --------------------------------------------------

    BALKEN_BREITE_AKTUELL = 32
    BALKEN_BREITE_VORJAHR = int(BALKEN_BREITE_AKTUELL * 0.75)  # etwas schmaler
    VERSATZ_VORJAHR = -int(BALKEN_BREITE_AKTUELL * 0.5)       # 25% nach links versetzt

    kanal_scale = alt.Scale(
        domain=["Theke", "App"],
        range=[COLOR_LOANS, COLOR_APP]
    )
    zeitraum_scale = alt.Scale(
        domain=["Aktuell", "Vorjahr"],
        range=[1.0, 0.4]  # Vorjahr deutlich transparenter, gleiche Farbe
    )

    chart_bar_aktuell = (
        alt.Chart(bars)
        .mark_bar(size=BALKEN_BREITE_AKTUELL)
        .encode(
            x=alt.X(
                "Monat_Label:N",
                sort=monate_label,
                title="Monat"
            ),
            y=alt.Y(
                "Ausleihen:Q",
                title="Ausleihen pro Monat"
            ),
            color=alt.Color("Kanal:N", legend=None, scale=kanal_scale),
            opacity=alt.Opacity("Zeitraum:N", title="Zeitraum", scale=zeitraum_scale, legend=None),
            tooltip=[
                alt.Tooltip("Monat_Label", title="Monat"),
                alt.Tooltip("Kanal", title="Ausleihart"),
                alt.Tooltip("Ausleihen", title="Ausleihen"),
            ]
        )
    )

    # --------------------------------------------------
    # Balken Vorjahr (schmaler, nach links versetzt,
    # gleiche Farben Theke/App, aber transparenter)
    # --------------------------------------------------

    chart_bar_vorjahr = (
        alt.Chart(bars_vorjahr)
        .mark_bar(
            size=BALKEN_BREITE_VORJAHR,
            xOffset=VERSATZ_VORJAHR
        )
        .encode(
            x=alt.X("Monat_Label:N", sort=monate_label),
            y=alt.Y("Ausleihen:Q"),
            color=alt.Color("Kanal:N", scale=kanal_scale, legend=None),
            opacity=alt.Opacity("Zeitraum:N", scale=zeitraum_scale),
            tooltip=[
                alt.Tooltip("Monat_Label", title="Monat"),
                alt.Tooltip("Kanal", title="Kanal"),
                alt.Tooltip("Zeitraum", title="Zeitraum"),
                alt.Tooltip("Ausleihen", title="Ausleihen")
            ]
        )
    )
    # Balken-Layer zusammenfassen
    bar_layer = alt.layer(chart_bar_vorjahr, chart_bar_aktuell)
    
    # --------------------------------------------------
    # Linie kumuliert (aktuelles Jahr nur bis heute, Vorjahr komplett)
    # --------------------------------------------------
    col0, col1,col1_2, col2,col2_2, col3 = st.columns([0.5,1,1,1,1,2])

    col1.markdown(
        f"""<span style="color:{COLOR_LOANS};"><strong>■</strong></span> <strong>Theke</strong>""",
        unsafe_allow_html=True,
    )
    col1_2.markdown(
        f"""<span style="color:{COLOR_APP};"><strong>■</strong></span> <strong>App</strong>""",
        unsafe_allow_html=True,
    )
    col2.markdown(f"""<span style="color:{COLOR_COMPARE_A};"><strong>━</strong></span> <strong> Kumulierte Ausleihen {aktuelles_jahr}<strong>""",unsafe_allow_html=True)
    col2_2.markdown(f"""<span style="color:{COLOR_PREVIOUS};"><strong>- - -</strong></span> <strong>Kumulierte Ausleihen {vorjahr}<strong>""",unsafe_allow_html=True)

    chart_line = (
        alt.Chart(line)
        .mark_line(point=True, strokeWidth=3)
        .encode(
            x=alt.X(
                "Monat_Label:N",
                sort=monate_label
            ),
            y=alt.Y(
                "Kumuliert:Q",
                axis=alt.Axis(
                    title="Gesamtausleihen",
                    orient="right"
                )
            ),
            color=alt.Color(
                "Linie:N",
                title="Gesamtausleihen",
                scale=alt.Scale(
                    domain=["Aktuelles Jahr","Vorjahr"],
                    range=[COLOR_COMPARE_A, COLOR_PREVIOUS]
                ),
                legend=None
            ),
            strokeDash=alt.condition(
                alt.datum.Jahr == vorjahr,
                alt.value([6, 4]),
                alt.value([1, 0])
            ),
            tooltip=[
                alt.Tooltip("Jahr:N"),
                alt.Tooltip("Monat_Label:N", title="Monat"),
                alt.Tooltip("Ausleihen:Q", title="Ausleihen Monat"),
                alt.Tooltip(f"Kumuliert_{aktuelles_jahr}:Q", title=f"Gesamtausleihen {aktuelles_jahr}"),
                alt.Tooltip(
                    f"Kumuliert_{vorjahr}:Q",
                    title=f"Gesamtausleihen {vorjahr}"
                ),
                alt.Tooltip(
                    "Differenz:Q",
                    title = "Δ Vorjahr",
                    format = "+.0f"
                ),
                alt.Tooltip(
                    "Differenz_%:Q",
                    title="Δ %",
                    format="+.1f"
                )
            ]
        )
    )

    # --------------------------------------------------
    # Layering
    # --------------------------------------------------

    chart = (
        alt.layer(
            bar_layer,
            chart_line
        )
        .resolve_scale(
            y="independent"
        )
        .properties(
            height=400
        )
    )

    home_trend_chart = chart

    st.altair_chart(
        chart,
        use_container_width=True
    )

    # --------------------------------------------------
    # KPI
    # --------------------------------------------------

    col1, col2 = st.columns(2)

    app_quote = (
        df_trend["Ausleihkanal"]
        .eq("App")
        .mean() * 100
        if not df_trend.empty
        else 0
    )
    df_vorjahr = df_beide[
        (df_beide["Jahr"] == vorjahr)
    ].copy()
    df_vorjahr_bis_stichtag = df_vorjahr[
        df_vorjahr["Ausleihdatum"] <= stichtag_vorjahr
    ].copy()

    app_quote_vorjahr = (
        df_vorjahr['Ausleihkanal']
        .eq("App")
        .mean()*100
        if not df_vorjahr.empty
        else 0
    )
    app_delta = app_quote - app_quote_vorjahr

    ausleihen_aktuell = len(df_trend)
    ausleihen_vorjahr = len(df_vorjahr_bis_stichtag)
    ausleihen_delta=ausleihen_aktuell - ausleihen_vorjahr
    veraenderung =(
        ausleihen_delta/ ausleihen_vorjahr *100
        if ausleihen_vorjahr > 0 else 0
    )
    home_extra_kpis = {
        "App-Anteil": (
            f"{app_quote:.1f} %"
            + f"\n{vorjahr}: {app_quote_vorjahr:.1f} %"
            + f"\n{app_delta:+.1f} Prozentpunkte"
        ),
        f"Aktuelle Ausleihen bis {heute.strftime('%d.%m.')}": (
            f"{ausleihen_aktuell:,}".replace(",", "'")
            + f"\n{vorjahr}: {ausleihen_vorjahr:,}".replace(",", "'")
            + f"\n{format_pdf_delta(ausleihen_aktuell, ausleihen_vorjahr)}"
        ),
    }
    with col1:
        farbe = SUCCESS if app_delta >= 0 else DANGER
        symbol = "🟢" if app_delta >= 0 else "🔴"

        kpi_box(
            "📱 App-Anteil",
            f"{app_quote:.1f} %",
            previous=f"{app_quote_vorjahr:.1f} %",
            previous_label=f"Vorjahr {str(vorjahr)}",
            subtext=f"{symbol} {app_delta:+.1f} %",
            color=farbe
        )

    with col2:
        farbe = SUCCESS if veraenderung >= 0 else DANGER
        symbol = "🟢" if veraenderung >= 0 else "🔴"
        kpi_box(
            f"📚 Aktuelle Ausleihen bis {heute.strftime("%d.%B")}",
            ausleihen_aktuell,
            previous=ausleihen_vorjahr,
            previous_label=f"Vorjahres Ausleihen bis {heute.strftime("%d.%B")} {vorjahr}",
            subtext = f"{symbol} {veraenderung:+.1f} %",
            color =farbe
    )

else:
    st.write("Keine Daten vorhanden")

has_smartlibrary_data = (
    df_smartlibrary is not None
    and not df_smartlibrary.empty
    and "erstellt" in df_smartlibrary.columns
)

if has_smartlibrary_data:
    # --------------------------------------------------
    # OpenLibrary aktueller Stand seit letztes BEDIENTEN ÖFFNUNG
    # --------------------------------------------------
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.subheader("OpenLibrary-Aktivitäten seit letzter bedienter Öffnungszeit")

if has_smartlibrary_data and (df_preferences is None or df_preferences.empty):
    st.info(
        "Noch keine Voreinstellungen im Cache gefunden. "
        "Nach dem nächsten Datenabruf wird das Layout `Voreinstellungen` mitgeladen."
    )
elif has_smartlibrary_data:
    returns_base = filtered_df_no_date.copy()
    smart_base = _filter_smartlibrary_visits(df_smartlibrary, filtered_users)
    latest_candidates = []
    if "Rückgabedatum" in returns_base.columns:
        latest_candidates.append(pd.to_datetime(returns_base["Rückgabedatum"], errors="coerce").max())
    if not smart_base.empty and "erstellt" in smart_base.columns:
        latest_candidates.append(pd.to_datetime(smart_base["erstellt"], errors="coerce").max())
    latest_candidates = [value for value in latest_candidates if pd.notna(value)]
    default_now = max(latest_candidates) if latest_candidates else pd.Timestamp.now()
    # Sobald produktiv-Daten drin sind,kann das weggelassen oder allenfalls weniger populär noch versteckt sein
    with st.expander("Test-Zeitpunkt", expanded=False):
        col_date, col_time = st.columns(2)
        with col_date:
            test_date = st.date_input(
                "Heute-Datum",
                value=default_now.date(),
                key="home_workload_test_date",
            )
        with col_time:
            test_time = st.time_input(
                "Uhrzeit",
                value=default_now.time().replace(microsecond=0),
                key="home_workload_test_time",
            )

    now = pd.Timestamp(datetime.combine(test_date, test_time))
    branch_col = "Zweigstelle_loan" if "Zweigstelle_loan" in returns_base.columns else "Zweigstelle"
    smart_branch_col = _find_branch_col(smart_base)
    branches = (
        returns_base[branch_col].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist()
        if branch_col in returns_base.columns
        else ["Gesamt"]
    )
    branches = sorted(branches) or ["Gesamt"]

    workload_rows = []
    for branch in branches:
        last_opening, source_col = _last_staffed_opening(df_preferences, branch, now)
        if last_opening is None:
            workload_rows.append({
                "Zweigstelle": branch,
                "Seit": "nicht erkannt",
                "App-Ausleihen": np.nan,
                "App-Rückgaben": np.nan,
                "Zutritte": np.nan,
                "Beobachtungstage": np.nan,
                "Hinweis": "Öffnungszeitenfeld nicht erkannt",
            })
            continue

        returns = returns_base.copy()
        if branch_col in returns.columns and branch != "Gesamt":
            returns = returns[returns[branch_col].astype(str).str.strip().eq(str(branch))]

        return_dates = pd.to_datetime(returns.get("Rückgabedatum"), errors="coerce")
        return_timestamps, timestamp_source = _find_return_timestamp(returns, return_dates)
        return_channel = (
            returns.get("Transaktion(2)", pd.Series("", index=returns.index))
            .fillna("")
            .astype(str)
            .str.strip()
        )
        app_return_mask = (
            (return_timestamps >= last_opening)
            & (return_timestamps <= now)
            & return_channel.str.startswith("App", na=False)
        )
        app_returns = returns[app_return_mask].copy()

        loan_dates = pd.to_datetime(
            returns.get("Ausleihdatum"),
            errors="coerce"
        )
        loan_timestamps= pd.to_datetime(
            returns.get("erstellt"),
            errors = "coerce"
        )
        # Sicherheitscheck: "erstellt" nur verwenden, wenn das Datum zum Ausleihdatum passt
        valid_loan_timestamp = (
            loan_timestamps.notna()
            & loan_dates.notna()
            & (loan_timestamps.dt.normalize()==loan_dates.dt.normalize())
        )

        loan_timestamps = loan_timestamps.where(valid_loan_timestamp)

        loan_channel = (
            returns.get(
                "Transaktion(1)",
                pd.Series("", index=returns.index)
            )
            .fillna("")
            .astype(str)
            .str.strip()
        )

        app_loan_mask = (
            (loan_timestamps >= last_opening)
            & (loan_timestamps <= now)
            & loan_channel.str.startswith("App", na=False)
        )

        app_loans = returns[app_loan_mask].copy()

        smart = smart_base.copy()
        if smart_branch_col in smart.columns and branch != "Gesamt":
            smart = smart[smart[smart_branch_col].astype(str).str.strip().eq(str(branch))]
        if not smart.empty and "erstellt" in smart.columns:
            smart["erstellt"] = pd.to_datetime(smart["erstellt"], errors="coerce")
            visits = smart[
                (smart["erstellt"] >= last_opening)
                & (smart["erstellt"] <= now)
            ]
            visit_count = len(visits)
        else:
            visit_count = np.nan


        wochentage = [
            "Montag",
            "Dienstag",
            "Mittwoch",
            "Donnerstag",
            "Freitag",
            "Samstag",
            "Sonntag",
        ]
        wochentag = wochentage[last_opening.weekday()]

        workload_rows.append({
            "Zweigstelle": branch,
            "Seit": f"{wochentag}, {last_opening.strftime('%d.%m.%Y %H:%M')}",
            "App-Ausleihen": len(app_loans),
            "App-Rückgaben": len(app_returns),
            "Zutritte": visit_count,
            "Beobachtungstage": max((now - last_opening).total_seconds() / 86400, 0),
            "Hinweis": f"{source_col or ''}; Zeitfeld: {timestamp_source or 'nur Datum'}",
        })

    workload = pd.DataFrame(workload_rows)

    # Numerische Werte bereinigen
    for col in ["App-Ausleihen", "App-Rückgaben", "Zutritte", "Beobachtungstage"]:
        workload[col] = pd.to_numeric(
            workload[col],
            errors="coerce"
        ).fillna(0)

    # Prüfen, ob überhaupt Aktivität vorhande ist
    has_worklaod = (
        workload[
            ["App-Ausleihen", "App-Rückgaben", "Zutritte"]
        ].sum().sum()>0
    )

    total_app_loans = int(workload["App-Ausleihen"].sum())
    total_app_returns = int(workload["App-Rückgaben"].sum())
    total_visits = int(workload["Zutritte"].sum())
    total_observation_days = workload["Beobachtungstage"].sum()
    loans_per_visit = (
        total_app_loans / total_visits
        if total_visits > 0
        else 0
    )
    returns_per_visit = (
        total_app_returns / total_visits
        if total_visits > 0
        else 0
    )
    visits_per_day = (
        total_visits / total_observation_days
        if total_observation_days > 0
        else 0
    )
    home_openlibrary_kpis = {
        "OpenLibrary App-Ausleihen": (
            f"{total_app_loans:,}".replace(",", "'")
            + f"\n{loans_per_visit:.2f} Ausleihen / Zutritt"
        ),
        "OpenLibrary App-Rückgaben": (
            f"{total_app_returns:,}".replace(",", "'")
            + f"\n{returns_per_visit:.2f} Rückgaben / Zutritt"
        ),
        "OpenLibrary Zutritte": (
            f"{total_visits:,}".replace(",", "'")
            + f"\n{visits_per_day:.1f} Zutritte / Tag"
        ),
    }

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_box(
            "App-Ausleihen",
            total_app_loans,
            subtext=f"{loans_per_visit:.2f} Ausleihen / Zutritt",
        )
    with c2:
        kpi_box(
            "App-Rückgaben",
            total_app_returns,
            subtext=f"{returns_per_visit:.2f} Rückgaben / Zutritt",
        )
    with c3:
        kpi_box(
            "Zutritte",
            total_visits,
            subtext=f"{visits_per_day:.1f} Zutritte / Tag",
        )
    with c4:
        recognized = workload["Seit"].ne("nicht erkannt").sum()
        kpi_box("Zweigstellen erkannt", f"{recognized}/{len(workload)}")

    if has_worklaod:
        st.markdown("<br>", unsafe_allow_html=True)
        # Plot-Daten je Zweigstelle vorbereiten
        workload_plot = workload.copy()

        workload_plot["App-Ausleihen"] = pd.to_numeric(
            workload_plot["App-Ausleihen"],
            errors="coerce"
        ).fillna(0)

        workload_plot["App-Rückgaben"] = pd.to_numeric(
            workload_plot["App-Rückgaben"],
            errors="coerce"
        ).fillna(0)

        workload_plot["Zutritte"] = pd.to_numeric(
            workload_plot["Zutritte"],
            errors="coerce"
        ).fillna(0)

        # Für Altair ins Long-Format bringen
        workload_long = workload_plot.melt(
            id_vars=["Zweigstelle"],
            value_vars=["App-Ausleihen","App-Rückgaben", "Zutritte"],
            var_name="Kennzahl",
            value_name="Anzahl",
        )

        # Sortierung nach gesamter Arbeitslast
        branch_order = (
            workload_plot
            .assign(
                Gesamt=workload_plot["App-Ausleihen"] + workload_plot["App-Rückgaben"] + workload_plot["Zutritte"]
            )
            .sort_values("Gesamt", ascending=False)["Zweigstelle"]
            .tolist()
        )

        workload_chart = (
            alt.Chart(workload_long)
            .mark_bar(
                cornerRadiusEnd=6,
                height=18,
            )
            .encode(
                y=alt.Y(
                    "Zweigstelle:N",
                    title=None,
                    sort=branch_order,
                    axis=alt.Axis(
                        labelFontSize=13,
                        labelLimit=220,
                    ),
                ),
                x=alt.X(
                    "Anzahl:Q",
                    title="Anzahl seit letzter bedienter Öffnungszeit",
                    axis=alt.Axis(
                        grid=True,
                        tickMinStep=1,
                    ),
                ),
                yOffset=alt.YOffset("Kennzahl:N"),
                color=alt.Color(
                    "Kennzahl:N",
                    title=None,
                    scale=alt.Scale(
                        domain=["App-Ausleihen","App-Rückgaben", "Zutritte"],
                        range=[COLOR_LOANS, COLOR_RETURNS, COLOR_VISITS],
                    ),
                ),
                tooltip=[
                    alt.Tooltip("Zweigstelle:N", title="Zweigstelle"),
                    alt.Tooltip("Kennzahl:N", title="Kennzahl"),
                    alt.Tooltip("Anzahl:Q", title="Anzahl", format=",.0f"),
                ],
            )
        )

        workload_labels = (
            alt.Chart(workload_long)
            .mark_text(
                align="left",
                baseline="middle",
                dx=5,
                fontSize=12,
                fontWeight="bold",
            )
            .encode(
                y=alt.Y(
                    "Zweigstelle:N",
                    sort=branch_order,
                ),
                yOffset=alt.YOffset("Kennzahl:N"),
                x=alt.X("Anzahl:Q"),
                text=alt.Text("Anzahl:Q", format=",.0f"),
                detail="Kennzahl:N",
            )
        )

        chart_height = max(180, len(branch_order) * 65)
        
        st.altair_chart(
            (workload_chart + workload_labels)
            .properties(height=chart_height)
            .configure_view(strokeWidth=0),
            use_container_width=True,
        )

        st.dataframe(
            workload.drop(columns=["Hinweis"], errors="ignore"),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Rückgaben verwenden das Ausleihe-Feld `geändert` als Zeitstempel, wenn dessen Datum dem Rückgabedatum entspricht."
        )

st.divider()
title_with_icon("Bericht exportieren", PDF,icon_size=34, level="subheader")

st.caption(
    "Erstellt einen kompakten PDF-Bericht mit den wichtigsten Kennzahlen, "
    "aktiven Filtern und dem Ausleihtrend der Startseite."
)

if st.button("📄 PDF erstellen", key="home_pdf_erstellen_button"):
    with st.spinner("PDF wird erstellt..."):
        home_kpis = {
            "Ausleihen": (
                f"{total_loans:,}".replace(",", "'")
                + f"\n{vorjahr}: {total_loans_old:,}".replace(",", "'")
                + f"\n{format_pdf_delta(total_loans, total_loans_old)}"
            ),
            "Offene Ausleihen": (
                f"{open_loans:,}".replace(",", "'")
                + f"\nÜberfällig: {ueberfaellig:,}".replace(",", "'")
            ),
            "Aktive Kund:innen": (
                f"{active_users:,}".replace(",", "'")
                + f"\n{vorjahr}: {active_users_old:,}".replace(",", "'")
                + f"\n{format_pdf_delta(active_users, active_users_old)}"
            ),
            "Neue Kund:innen": (
                f"{new_users:,}".replace(",", "'")
                + f"\n{vorjahr}: {new_users_old:,}".replace(",", "'")
                + f"\n{format_pdf_delta(new_users, new_users_old)}"
            ),
        }
        home_kpis.update(home_extra_kpis)

        home_kpi_sections = []
        if home_openlibrary_kpis:
            home_kpi_sections.append((
                "Aktuelle Arbeitslast OpenLibrary",
                home_openlibrary_kpis,
            ))

        home_charts = []
        if home_trend_chart is not None:
            home_charts.append((
                f"Ausleihtrend {aktuelles_jahr} vs. {vorjahr}",
                home_trend_chart,
            ))

        if not offene_medienart.empty:
            offene_chart = (
                alt.Chart(offene_medienart.head(10))
                .mark_bar(color=COLOR_LOANS)
                .encode(
                    x=alt.X("Offen:Q", title="Offene Ausleihen"),
                    y=alt.Y("Medienart:N", title="Medienart", sort="-x"),
                    tooltip=[
                        alt.Tooltip("Medienart:N", title="Medienart"),
                        alt.Tooltip("Offen:Q", title="Offen"),
                        alt.Tooltip("Überfällig:Q", title="Überfällig"),
                    ],
                )
                .properties(height=280)
            )
            home_charts.append(("Offene Ausleihen nach Medienart", offene_chart))

        report = build_report_pdf(
            title=f"Bibliothek {BIBLIOTHEK}",
            subtitle=f"Kompakter Statusbericht {aktuelles_jahr}.",
            kpis=home_kpis,
            filters=build_home_filter_summary(filter_state),
            kpi_title=f"Kennzahlen {aktuelles_jahr}",
            kpi_sections=home_kpi_sections,
            charts=home_charts,
        )

    if report.failed_charts:
        st.warning(
            "⚠️ Folgende Diagramme konnten nicht ins PDF eingebettet werden:\n\n"
            + "\n".join(f"- **{titel}**: {fehler}" for titel, fehler in report.failed_charts)
        )

    st.success("PDF wurde erstellt.")
    st.download_button(
        "⬇️ PDF herunterladen",
        data=report.pdf_bytes,
        file_name=f"leitungsbericht_{datetime.now():%Y%m%d_%H%M}.pdf",
        mime="application/pdf",
    )

