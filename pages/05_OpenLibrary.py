import streamlit as st
from components.sidebar import render_sidebar
from utils import apply_filters, load_data, apply_group_mapping
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

filtered_df = apply_filters(
    df_ausleihe,
    filters["date_range"],
    filters.get("Zweigstelle", []),
    filters.get("Medienart", []),
    filters.get("Benutzergruppe", []),
    filters.get("Kategorie Alter", [])
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

if filters["date_range"] is not None:
    start, ende = filters["date_range"]

    start = pd.Timestamp(start)
    ende = pd.Timestamp(ende) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    df_open = df_open[
        df_open["erstellt"].between(start, ende)
    ]

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
# =====================================================
# KENNZAHLEN
# =====================================================

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

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "🏛️ Zutritte",
    f"{gesamt_zutritte:,}"
)

c2.metric(
    "👤 Besucher",
    f"{anzahl_besucher:,}"
)

c3.metric(
    "📅 Zeitraum",
    f"{zeitraum} Tage"
)

c4.metric(
    "📈 Ø Zutritte / Tag",
    durchschnitt
)
col1, col2 = st.columns(2)
# =====================================================
# ZUTRITTE NACH STUNDE
# =====================================================
with col1:
    st.subheader("🕒 Zutritte nach Stunde")

    stunden = (
        df_open
        .groupby("Stunde")
        .size()
        .reset_index(name="Zutritte")
    )

    chart = (
        alt.Chart(stunden)
        .mark_bar()
        .encode(
            x=alt.X("Stunde:O"),
            y="Zutritte:Q",
            tooltip=["Stunde","Zutritte"]
        )
        .properties(height=300)
    )

    st.altair_chart(chart, use_container_width=True)
# =====================================================
# ZUTRITTE NACH WOCHENTAG
# =====================================================
with col2:
    st.subheader("📅 Zutritte nach Wochentag")

    reihenfolge = [
        "Montag",
        "Dienstag",
        "Mittwoch",
        "Donnerstag",
        "Freitag",
        "Samstag",
        "Sonntag"
    ]

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


# =====================================================
# ZUTRITTE PRO Woche
# =====================================================

st.subheader("📈 Zutritte pro Tag")

reihenfolge = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag"
]
df_open["Jahr"] = df_open["erstellt"].dt.isocalendar().year
df_open["Kalenderwoche"] = df_open["erstellt"].dt.isocalendar().week
df_open["Wochentag"] = df_open["erstellt"].dt.day_name(locale="de_CH")


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
ferien = [
    f
    for f in config.get("ferien", [])
    if f.get("aktiv", True)
]
with st.expander("Ferien markieren"):
    aktive_ferien = st.multiselect(
        "Ferien aus-/abwählen",
        options=[f["name"] for f in ferien],
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
    fields=[
        "Jahr",
        "Kalenderwoche"
    ],
    empty="none"
)
punkte = (
    alt.Chart(pro_woche)
    .mark_circle(size=80)
    .encode(
        x="Kalenderwoche:Q",
        y="Zutritte:Q",
        color="Jahr:N",
        tooltip=[
            "Jahr",
            alt.Tooltip("Kalenderwoche:Q", title="KW"),
            alt.Tooltip("Woche:N", title="Zeitraum"),
            "Zutritte"
        ]
    )
    .add_params(selection)
)
highlight = (
    alt.Chart(pro_woche)
    .mark_circle(
        size=220,
        filled=False,
        stroke="red",
        strokeWidth=3
    )
    .encode(
        x="Kalenderwoche:Q",
        y="Zutritte:Q"
    )
    .transform_filter(selection)
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
    .mark_bar(size=25)
    .encode(
        y=alt.Y(
            "Wochentag:N",
            sort=reihenfolge,
            title=""
        ),
        x=alt.X(
            "Zutritte:Q"
        ),
        tooltip=[
            "Wochentag",
            "Zutritte"
        ]
    )
    .properties(
        width=350,
        height=250,
        title="Verteilung innerhalb der gewählten Kalenderwoche"
    )
)
chart = (
    alt.layer(
        ferien_layer,
        linien,
        punkte,
        highlight
    )
    .resolve_scale(
        color="independent"
    )
    .properties(
        width=850,
        height=420
    )
)
gesamtchart = (
    alt.vconcat(
        chart,
        detail
    )
)

st.altair_chart(
    gesamtchart,
    use_container_width=False
)
