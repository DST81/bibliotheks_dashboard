import streamlit as st
from components.sidebar import render_sidebar
from components.ui import kpi_box
from src.utils import  load_data, apply_group_mapping
from src.filters import apply_filters
import streamlit as st
import json
from pathlib import Path
import os
import pandas as pd
import altair as alt


st.set_page_config(page_title="Open-Library-Zutritte", page_icon="📲", layout="wide")
st.title("📲 OpenLibrary Zutritte")
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
df_smart =data.get("smartlibrary")

if df_users is None:
    st.warning("Keine Nutzerdaten verfügbar.")
    st.stop()

if df_smart is None:
    st.warning("Keine OpenLibrary-Protokolldaten verfügbar.")
    st.stop()
df_users = apply_group_mapping(df_users, config)
filters = render_sidebar(df_ausleihe, config)

min_datum = df_smart['erstellt'].min()
max_datum = df_smart['erstellt'].max()

st.sidebar.caption(
    f"Verfügbare Daten: {min_datum:%d.%m.%Y} bis {max_datum:%d.%m.%Y}"
)
filtered_df = apply_filters(
    df_ausleihe,
    filters["date_range"],
    filters.get("Zweigstelle", []),
    filters.get("Medienart", []),
    filters.get("Benutzergruppe", []),
    filters.get("Kategorie Alter", [])
)
# Datumsfelder in datetime umwandeln
df_users["Ablauf_Beitrag"] = pd.to_datetime(
    df_users["Ablauf_Beitrag"],
    errors="coerce"
)

for i in range(1, 11):
    col = f"Abo_bezahlt_bis({i})"
    if col in df_users.columns:
        df_users[col] = pd.to_datetime(
            df_users[col],
            errors="coerce"
        )

# =====================================================
# DATEN VORBEREITEN
# =====================================================

df_open = df_smart.copy()
user_cols = ["Nummer", "Benutzergruppe"]

df_open = df_open.merge(
    df_users[user_cols],
    on="Nummer",
    how="left"
)
if filters.get("Benutzergruppe"):
    df_open = df_open[
        df_open["Benutzergruppe"].isin(filters["Benutzergruppe"])
    ]
df_open["erstellt"] = pd.to_datetime(
    df_open["erstellt"],
    errors="coerce"
)

date_range = filters.get("date_range")

if isinstance(date_range, (list,tuple)) and len(date_range)==2:
    start, ende = date_range
    start = pd.Timestamp(start)
    ende = pd.Timestamp(ende) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    df_open = df_open[
        df_open['erstellt'].between(start,ende)
    ]
if df_open.empty:
    st.info("Für die gewählten Filter sind keine Zutritte vorhanden")
    st.stop()
# Nur gültige Einträge
df_open = df_open[
    df_open["erstellt"].notna()
]

# Leere Benutzernummern entfernen
df_open["Nummer"] = (
    df_open["Nummer"]
    .fillna("")
    .astype(str)
    .str.strip()
)

df_open = df_open[df_open["Nummer"] != ""]

# Hilfsspalten
df_open["Datum"] = df_open["erstellt"].dt.date
df_open["Stunde"] = df_open["erstellt"].dt.hour

wochentage = {
    0: "Montag",
    1: "Dienstag",
    2: "Mittwoch",
    3: "Donnerstag",
    4: "Freitag",
    5: "Samstag",
    6: "Sonntag"
}

df_open["Wochentag"] = (
    df_open["erstellt"]
    .dt.dayofweek
    .map(wochentage)
)

# Openlibrary-Abos
heute= pd.Timestamp.today().normalize()

#Nur Benutzer mit OpenLibrary-Benutzergruppe oder Abo Open

def hat_openlibrary(row):
    #Benutzergrpppe
    if 'open' in str(row.get('Benutzergruppe', '')).lower():
        return True

    # Abos 1-10
    for i in range(1, 11):
        abo = row.get(f'Abo_Name({i})')

        if (
            pd.notna(abo)
            and 'open' in str(abo).lower()
        ):
            return True
    return False

def abo_abgelaufen(row):
    # Abo Benutzerbeitrag (nur wenn Benutzergruppe OpenLibrary)
    if (
        'open' in str(row.get('Benutzergruppe', '')).lower()
        and pd.notna(row.get('Ablauf_Beitrag'))
        and row['Ablauf_Beitrag']< heute
    ):
        return True

    # OpenLibrary-Abos
    for i in range(1,11):
        abo = row.get(f'Abo_Name({i})')
        bezahlt_bis = row.get(f'Abo_bezahlt_bis({i})')

        if (
            pd.notna(abo)
            and 'open' in str(abo).lower()
            and pd.notna(bezahlt_bis)
            and bezahlt_bis < heute
        ):
            return True
    return False

# Benutzer mit mindestens einem OpenLibrary-Zugang
open_users = df_users[
    df_users.apply(hat_openlibrary, axis=1)
].copy()

open_users['Abo_abgelaufen'] =open_users.apply(
    abo_abgelaufen,
    axis=1
)

anzahl_open_abos = len(open_users)
anzahl_abgelaufen = open_users['Abo_abgelaufen'].sum()
anzahl_aktiv = anzahl_open_abos - anzahl_abgelaufen

quote_abgelaufen = (
    anzahl_abgelaufen / anzahl_open_abos *100
    if anzahl_open_abos > 0
    else 0
)
    
# =====================================================
# KENNZAHLEN
# =====================================================
df_open["Jahr"] = df_open["erstellt"].dt.isocalendar().year
df_open["Kalenderwoche"] = df_open["erstellt"].dt.isocalendar().week
df_open["Wochentag"] = df_open["erstellt"].dt.day_name(locale="de_CH")


gesamt_zutritte = len(df_open)

anzahl_besucher = df_open["Nummer"].nunique()

zeitraum = (
    df_open["Datum"].max()
    -
    df_open["Datum"].min()
).days + 1

durchschnitt = round(
    gesamt_zutritte / zeitraum,
    1
)
wochen = (
    df_open
    .groupby(["Jahr","Kalenderwoche"])
    .size()
)
durchschnitt_pro_woche = round(wochen.mean(),1)

monate = (
    df_open
    .groupby([
        df_open['erstellt'].dt.year,
        df_open['erstellt'].dt.month
    ])
    .size()
)
durchschnitt_pro_monat = round(monate.mean(), 1)
c1, c2 =st.columns(2)
with c1:
    kpi_box("🔑 Aktive OpenLibrary-Abos",anzahl_aktiv,previous=anzahl_open_abos,previous_label="Total registrierte:")

with c2:
    farbe = "#C62828" if quote_abgelaufen > 10 else "#2E7D32"
    kpi_box("⚠️ Abgelaufene Abos",anzahl_abgelaufen,previous=f"{quote_abgelaufen:.1f} %",previous_label="Anteil",color=farbe)

st.markdown("<br>", unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)

with c1:
    kpi_box("🏛️ Total Zutritte im Zeitraum",gesamt_zutritte)

with c2:
    kpi_box("👤 Total Besucher im Zeitraum",anzahl_besucher)

with c3:
    kpi_box("📅 Zeitraum",zeitraum, suffix= "Tage")



st.markdown("<br>", unsafe_allow_html=True)  

# =====================================================
# ZUTRITTE PRO Woche
# =====================================================

st.subheader("📈 Zutritte nach Kalenderwoche - Woche auswählen")

reihenfolge = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag"
]

wochentage = (
    df_open
    .groupby(["Jahr","Kalenderwoche","Wochentag"])
    .size()
    .reset_index(name="Zutritte")
)

df_open["Wochentag"] = pd.Categorical(
    df_open["Wochentag"],
    categories=reihenfolge,
    ordered=True
)

pro_tag = (
    df_open
    .groupby(
        [
            "Jahr",
            "Kalenderwoche",
            "Wochentag"
        ]
    )
    .size()
    .reset_index(name="Zutritte")
)
pro_woche = (
    df_open
    .groupby(["Jahr", "Kalenderwoche"])
    .size()
    .reset_index(name="Zutritte")
)
pro_woche["Wochenstart"] = pd.to_datetime(
    pro_woche["Jahr"].astype(str)
    + "-W"
    + pro_woche["Kalenderwoche"].astype(str).str.zfill(2)
    + "-1",
    format="%G-W%V-%u"
)

pro_woche["Wochenende"] = pro_woche["Wochenstart"] + pd.Timedelta(days=6)

pro_woche["Woche"] = (
    pro_woche["Wochenstart"].dt.strftime("%d.%m.")
    + " – "
    + pro_woche["Wochenende"].dt.strftime("%d.%m.%Y")
)

letzte_woche= (
    pro_woche
    .sort_values(["Jahr", "Kalenderwoche"])
    .iloc[-1]
)

ferien = [
    f
    for f in config.get("ferien", [])
    if f.get("aktiv", True)
]

aktive_ferien = st.pills(
    "Ferien aus-/abwählen",
    options=[f["name"] for f in ferien],
    selection_mode="multi",
    default=[f["name"] for f in ferien]
)

ferien_bereiche = []

for f in ferien:

    if f["name"] not in aktive_ferien:
        continue

    start = int(f["start_kw"])
    ende = int(f["end_kw"])

    # normale Ferien
    if start <= ende:

        ferien_bereiche.append({
            "Ferien": f["name"],
            "start_kw": start,
            # +1 damit die Endwoche komplett eingefärbt wird
            "end_kw": ende + 0.5,
            "farbe": f["farbe"]
        })

    # Jahreswechsel
    else:

        ferien_bereiche.append({
            "Ferien": f["name"],
            "start_kw": start,
            "end_kw": 52,
            "farbe": f["farbe"]
        })

        ferien_bereiche.append({
            "Ferien": f["name"],
            "start_kw": 0.5,
            "end_kw": ende + 0.5,
            "farbe": f["farbe"]
        })
selection = alt.selection_point(
    name="kw_select",
    fields=[
        "Jahr",
        "Kalenderwoche"
    ],
    empty="none"
)
punkte = (
    alt.Chart(pro_woche)
    .mark_circle(
        size=100
        )
    .encode(
        x="Kalenderwoche:Q",
        y="Zutritte:Q",
        color=alt.condition(
            selection,
            alt.value("red"),
            alt.Color("Jahr:N", legend=None)
        ),
        tooltip=[
            "Jahr",
            alt.Tooltip("Kalenderwoche:Q", title="KW"),
            alt.Tooltip("Woche:N", title="Zeitraum"),
            "Zutritte"
        ]
    )
    .add_params(selection)
)

ferien_df = pd.DataFrame(ferien_bereiche)

ferien_layer = alt.layer()

for _, f in ferien_df.iterrows():

    layer = (
        alt.Chart(pd.DataFrame([f]))
        .mark_rect(
            opacity=0.20
        )
        .encode(
            x="start_kw:Q",
            x2="end_kw:Q",
            color=alt.value(f["farbe"]),
            tooltip=[
                alt.Tooltip("Ferien:N"),
                alt.Tooltip("start_kw:Q", title="Start KW"),
                alt.Tooltip("end_kw:Q", title="Ende KW")
            ]
        )
    )

    ferien_layer += layer
linien = (
    alt.Chart(pro_woche)
    .mark_line(point=True, strokeWidth=3)
    .encode(
        x=alt.X(
            "Kalenderwoche:Q",
            scale=alt.Scale(domain=[1,53], nice=False),
            axis=alt.Axis(values=list(range(1, 53))),
            title="Kalenderwoche"
        ),
        y=alt.Y(
            "Zutritte:Q",
            title="Zutritte"
        ),
        color=alt.Color(
            "Jahr:N",
            title="Jahr",
            legend=alt.Legend(
                orient="top",
                direction="horizontal"
            )
        ),
        tooltip=[
            "Jahr",
            "Kalenderwoche",
            "Zutritte"
        ]
    )
    .add_params(selection)
)

detail = (
    alt.Chart(pro_tag)
    .transform_filter(selection)
    .transform_window(
        row_number='row_number()',
        sort=[
            alt.SortField("Jahr", order="descending"),
            alt.SortField("Kalenderwoche", order="descending")
        ]
    )
    .transform_filter(
        "datum.row_number <8"
    )
    .mark_bar(size=25)
    .encode(
        y=alt.Y(
            "Wochentag:N",
            sort=reihenfolge,
            title=""
        ),
        x=alt.X(
            "Zutritte:Q",
            axis=alt.Axis(format="d")
        ),
        tooltip=[
            "Wochentag",
            "Zutritte"
        ]
    )
    .properties(
        width=400,
        height=320
    )
)
chart = (
    alt.layer(
        ferien_layer,
        linien,
        punkte
    )
    .resolve_scale(
        color="independent"
    )
    .properties(
        width=600,
        height=320,
    )
)
titel_text = f"Verteilung der Zutritte vom  {letzte_woche['Woche']}"

titel = (
    alt.Chart(pro_woche)
    .transform_filter(selection)
    .transform_window(
        row_number="row_number()",
        sort=[
            alt.SortField("Jahr", order="descending"),
            alt.SortField("Kalenderwoche", order="descending")
        ]
    )
    .transform_filter(
        "datum.row_number == 1"
    )
    .transform_calculate(
        label="'Verteilung der Zutritte vom ' + datum.Woche"
    )
    .mark_text(
        fontSize=16,
        fontWeight="bold",
        align="left",
        baseline="middle"
    )
    .encode(
        text="label:N"
    )
    .properties(
        width=100,
        height=30
    )
)
gesamtchart = (
    alt.hconcat(
        chart,
        titel,
        detail
    )
)

st.altair_chart(
    gesamtchart,
    on_select="rerun",
    use_container_width=False
)
# =====================================================
# ZUTRITTE NACH STUNDE
# =====================================================
reihenfolge = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag"
]

st.subheader("🕒 Zutritte nach Stunde")

ausgewaehlte_tage = st.pills(
    "Wochentage",
    reihenfolge,
    selection_mode='multi',
    default=reihenfolge
)
stunden = (
    df_open[
        df_open["Wochentag"].isin(ausgewaehlte_tage)
    ]
    .groupby(["Stunde", "Wochentag"])
    .size()
    .reset_index(name="Zutritte")
)

stunden["Wochentag"] = pd.Categorical(
    stunden["Wochentag"],
    categories=reihenfolge,
    ordered=True
)
stunden["Stunden_label"] = stunden["Stunde"].map(lambda x: f"{x:02d}:00")

chart = (
    alt.Chart(stunden)
    .mark_bar()
    .encode(
        x=alt.X(
            "Stunden_label:N",
            sort=[f"{i:02d}:00" for i in range(24)],
            title="Uhrzeit"
        ),
        xOffset=alt.XOffset(
            "Wochentag:N",
            sort=reihenfolge
        ),
        y=alt.Y(
            "Zutritte:Q",
            title="Zutritte"
        ),
        color=alt.Color(
            "Wochentag:N",
            sort=reihenfolge,
            legend=alt.Legend(orient="bottom")
        ),
        tooltip=[
            alt.Tooltip("Wochentag:N"),
            alt.Tooltip("Stunden_label:N", title="Uhrzeit"),
            alt.Tooltip("Zutritte:Q")
        ]
    )
    .properties(height=320)
)

st.altair_chart(chart, use_container_width=True)
# =====================================================
# ZUTRITTE NACH WOCHENTAG
# =====================================================

st.subheader("📅 Zutritte nach Wochentag")


tage = (
    df_open
    .groupby("Wochentag")
    .size()
    .reindex(reihenfolge)
    .fillna(0)
    .reset_index(name="Zutritte")
)

chart = (
    alt.Chart(tage)
    .mark_bar()
    .encode(
        x=alt.X(
            "Wochentag:N",
            sort=reihenfolge
        ),
        y="Zutritte:Q",
        tooltip=["Wochentag","Zutritte"]
    )
    .properties(height=300)
)

st.altair_chart(chart, use_container_width=True)

c1, c2, c3 = st.columns(3)
with c1:
    kpi_box("📈 Ø Zutritte / Tag",durchschnitt)

with c2:
    kpi_box("📅 Ø / Woche",durchschnitt_pro_woche)

with c3:
    kpi_box("🗓️ Ø / Monat",durchschnitt_pro_monat)

stunden_tag = (
    df_open
    .groupby(["Wochentag", "Stunde"])
    .size()
    .reset_index(name="Zutritte")
)

stunden_tag["Wochentag"] = pd.Categorical(
    stunden_tag["Wochentag"],
    categories=reihenfolge,
    ordered=True
)

heatmap = (
    alt.Chart(stunden_tag)
    .mark_rect()
    .encode(
        x=alt.X("Stunde:O", title="Stunde"),
        y=alt.Y("Wochentag:N", sort=reihenfolge),
        color=alt.Color("Zutritte:Q", title="Zutritte"),
        tooltip=[
            "Wochentag",
            "Stunde",
            "Zutritte"
        ]
    )
    .properties(height=280)
)

st.altair_chart(heatmap, use_container_width=False)
stunden_tag = (
    df_open
    .groupby(["Stunde", "Wochentag"])
    .size()
    .reset_index(name="Zutritte")
)

