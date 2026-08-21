import streamlit as st
import json
from pathlib import Path
import os
from html import escape
import pandas as pd
import numpy as np
import altair as alt

from components.ui import kpi_box, title_with_icon
from components.icons import APP, OPEN, CALENDAR
from src.filters import get_sidebar_filters
from src.theme import (
    SUCCESS,
    DANGER,
    COLOR_LOANS,
    COLOR_VISITS,
    COLOR_HOLIDAY,
    COLOR_WEEKDAYS,
    TEXT,
)


st.set_page_config(page_title="Open-Library-Zutritte", page_icon="assets/app_user.svg", layout="wide")

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
if "data" not in st.session_state or st.session_state["data"] is None:
    st.error("Keine Daten geladen. Bitte starten Sie das Dashboard über die Startseite.")
    st.stop()

data = st.session_state["data"]
df_users = data.get("users", pd.DataFrame())
df_smart = data.get("smartlibrary", pd.DataFrame())
df_loans = data.get("loans", pd.DataFrame())

if df_smart is None or df_smart.empty:
    st.info("Keine OpenLibrary-Protokolldaten verfügbar.")
    st.stop()

filtered_users, filtered_smart, filter_info = get_sidebar_filters(
    df_users=df_users,
    df_extra=df_smart,
    prefix="openlibrary",
    enable_date_filter=True,
    date_col_name="erstellt",
    enable_first_loan_toggle=False,
    show_metrics=True,
    expander_defaults={
        "target": False,
        "loans": True,
        "catalog": False,
    },
    expander_labels={
        "loans": "🔓 Zutritte",
    },
)

df_users = filtered_users.copy()
df_smart = filtered_smart.copy() if filtered_smart is not None else pd.DataFrame()

if "erstellt" in df_smart.columns:
    min_datum = pd.to_datetime(df_smart["erstellt"], errors="coerce").min()
    max_datum = pd.to_datetime(df_smart["erstellt"], errors="coerce").max()
    if pd.notna(min_datum) and pd.notna(max_datum):
        st.sidebar.caption(
            f"Verfügbare Zutritte: {min_datum:%d.%m.%Y} bis {max_datum:%d.%m.%Y}"
        )
# Datumsfelder in datetime umwandeln
if "Ablauf_Beitrag" in df_users.columns:
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

if "Nummer" in df_open.columns:
    df_open["Nummer"] = (
        df_open["Nummer"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

if "Nummer" in df_open.columns and "Nummer" in df_users.columns:
    aktive_benutzer = (
        df_users["Nummer"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )
    df_open = df_open[df_open["Nummer"].isin(aktive_benutzer)]

user_cols = [col for col in ["Nummer", "Benutzergruppe"] if col in df_users.columns]

if "Nummer" in df_open.columns and "Nummer" in df_users.columns and user_cols:
    df_open = df_open.merge(
        df_users[user_cols].assign(Nummer=df_users["Nummer"].astype(str).str.strip()).drop_duplicates("Nummer"),
        on="Nummer",
        how="left"
    )

df_open["erstellt"] = pd.to_datetime(
    df_open["erstellt"],
    errors="coerce"
)

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
besucher_pro_tag = round(
    anzahl_besucher / zeitraum,
    1,
)
zutritte_pro_besucher = round(
    gesamt_zutritte / anzahl_besucher,
    1,
) if anzahl_besucher > 0 else 0

df_loans_open = pd.DataFrame()
if (
    df_loans is not None
    and not df_loans.empty
    and "Ausleihperson" in df_loans.columns
    and "Ausleihdatum" in df_loans.columns
):
    zutrittskunden = (
        df_open["Nummer"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )
    start_datum = df_open["Datum"].min()
    ende_datum = df_open["Datum"].max()

    df_loans_open = df_loans.copy()
    df_loans_open["Ausleihperson"] = (
        df_loans_open["Ausleihperson"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    df_loans_open["Ausleihdatum"] = pd.to_datetime(
        df_loans_open["Ausleihdatum"],
        errors="coerce",
    )
    df_loans_open = df_loans_open[
        df_loans_open["Ausleihperson"].isin(zutrittskunden)
        & df_loans_open["Ausleihdatum"].dt.date.between(start_datum, ende_datum)
    ].copy()
    df_loans_open["Jahr"] = df_loans_open["Ausleihdatum"].dt.isocalendar().year
    df_loans_open["Kalenderwoche"] = df_loans_open["Ausleihdatum"].dt.isocalendar().week
    if "erstellt" in df_loans_open.columns:
        df_loans_open["Ausleihzeit"] = pd.to_datetime(
            df_loans_open["erstellt"],
            errors="coerce",
        )
    else:
        df_loans_open["Ausleihzeit"] = df_loans_open["Ausleihdatum"]

    df_loans_open["Stunde"] = df_loans_open["Ausleihzeit"].dt.hour
    df_loans_open["Wochentag"] = (
        df_loans_open["Ausleihzeit"]
        .dt.dayofweek
        .map(wochentage)
    )

ausleihen_zutrittskunden = len(df_loans_open)
ausleihen_pro_zutritt = round(
    ausleihen_zutrittskunden / gesamt_zutritte,1
    if gesamt_zutritte > 0
    else 0
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

col1, col2=st.columns([3,1])
with col1:
    title_with_icon("OpenLibrary Zutritte", APP, icon_size=38)

with col2:
    kpi_box("📅 Zeitraum",zeitraum, suffix= "Tage")

st.markdown("<br>", unsafe_allow_html=True)

abo_col1, abo_col2 = st.columns(2)
with abo_col1:
    kpi_box("🔑 Aktive OpenLibrary-Abos",anzahl_aktiv,previous=anzahl_open_abos,previous_label="Total registrierte:")

with abo_col2:
    farbe = DANGER if quote_abgelaufen > 10 else SUCCESS
    kpi_box("⚠️ Abgelaufene Abos",anzahl_abgelaufen,previous=f"{quote_abgelaufen:.1f} %",previous_label="Anteil",color=farbe)

st.markdown("<br>", unsafe_allow_html=True)

nutzung_col1, nutzung_col2, nutzung_col3, c1,c2,c3 = st.columns(6)

with nutzung_col1:
    kpi_box(
        "🏛️ Zutritte im Zeitraum",
        gesamt_zutritte,
        previous=durchschnitt,
        previous_label="Zutritte pro Tag",
    )

with nutzung_col2:
    kpi_box(
        "👤 Besucher im Zeitraum",
        anzahl_besucher,
        previous=zutritte_pro_besucher,
        previous_label="Zutritte / Besucher",
    )

with nutzung_col3:
    kpi_box(
        "📚 Ausleihen Zutrittskunden",
        ausleihen_zutrittskunden,
        previous=ausleihen_pro_zutritt,
        previous_label="Ø-Ausleihen / Zutritt",
    )


with c1:
    kpi_box("📈 Ø Zutritte / Tag",durchschnitt)

with c2:
    kpi_box("📅 Ø / Woche",durchschnitt_pro_woche)

with c3:
    kpi_box("🗓️ Ø / Monat",durchschnitt_pro_monat)

st.markdown("<br>", unsafe_allow_html=True)  

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

openlibrary_config = config.get("openlibrary", {})
oeffnung_start = int(openlibrary_config.get("start_stunde", 6))
oeffnung_ende = int(openlibrary_config.get("end_stunde", 23))
oeffnung_start = min(max(oeffnung_start, 0), 23)
oeffnung_ende = min(max(oeffnung_ende, oeffnung_start), 23)
stunden_range = range(oeffnung_start, oeffnung_ende + 1)
stunden_sort = [f"{i:02d}-{i + 1:02d}" for i in stunden_range]

tage_anzahl = pd.Series(0, index=reihenfolge, dtype=int)
if not df_open.empty:
    alle_tage = pd.date_range(
        df_open["Datum"].min(),
        df_open["Datum"].max(),
        freq="D",
    )
    tage_anzahl = (
        pd.Series([reihenfolge[tag.weekday()] for tag in alle_tage])
        .value_counts()
        .reindex(reihenfolge)
        .fillna(0)
        .astype(int)
    )

# ZUTRITTE / AUSLEIHEN PRO WOCHE
# =====================================================

title_with_icon("Zutritte und Ausleihen nach Kalenderwoche", OPEN, icon_size=34, level="subheader")



df_open["Wochentag"] = pd.Categorical(
    df_open["Wochentag"],
    categories=reihenfolge,
    ordered=True
)

pro_woche = (
    df_open
    .groupby(["Jahr", "Kalenderwoche"])
    .size()
    .reset_index(name="Zutritte")
)
ausleihen_pro_woche = (
    df_loans_open
    .groupby(["Jahr", "Kalenderwoche"])
    .size()
    .reset_index(name="Ausleihen")
    if not df_loans_open.empty
    else pd.DataFrame(columns=["Jahr", "Kalenderwoche", "Ausleihen"])
)
pro_woche = pro_woche.merge(
    ausleihen_pro_woche,
    on=["Jahr", "Kalenderwoche"],
    how="left",
)
pro_woche["Ausleihen"] = pro_woche["Ausleihen"].fillna(0).astype(int)
pro_woche["Ausleihen_pro_Zutritt"] = np.where(
    pro_woche["Zutritte"] > 0,
    pro_woche["Ausleihen"] / pro_woche["Zutritte"],
    0,
).round(1)
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
    + " - "
    + pro_woche["Wochenende"].dt.strftime("%d.%m.%Y")
)
pro_woche["KW_Label"] = (
    pro_woche["Jahr"].astype(str)
    + " / KW "
    + pro_woche["Kalenderwoche"].astype(str).str.zfill(2)
)
pro_woche["Auswahl"] = pro_woche["KW_Label"] + " (" + pro_woche["Woche"] + ")"
pro_woche = pro_woche.sort_values("Wochenstart").reset_index(drop=True)
pro_woche_chart = pro_woche.melt(
    id_vars=[
        "Jahr",
        "Kalenderwoche",
        "Wochenstart",
        "Woche",
        "KW_Label",
    ],
    value_vars=[
        "Zutritte",
        "Ausleihen",
    ],
    var_name="Kennzahl",
    value_name="Anzahl",
)

ferien = [
    f
    for f in config.get("ferien", [])
    if f.get("aktiv", True)
]

aktive_ferien = st.pills(
    "Ferien anzeigen",
    options=[f["name"] for f in ferien],
    selection_mode="multi",
    default=[f["name"] for f in ferien],
    key="openlibrary_ferien_auswahl",
)

ferien = [
    f
    for f in ferien
    if f["name"] in aktive_ferien
]

ferien_bereiche = []
for f in ferien:
    start_kw = int(f["start_kw"])
    ende_kw = int(f["end_kw"])

    for jahr in pro_woche["Jahr"].dropna().unique():
        jahr = int(jahr)
        if start_kw <= ende_kw:
            wochen = pro_woche[
                (pro_woche["Jahr"] == jahr)
                & pro_woche["Kalenderwoche"].between(start_kw, ende_kw)
            ]
        else:
            wochen = pro_woche[
                (pro_woche["Jahr"] == jahr)
                & (
                    (pro_woche["Kalenderwoche"] >= start_kw)
                    | (pro_woche["Kalenderwoche"] <= ende_kw)
                )
            ]

        if wochen.empty:
            continue

        ferien_bereiche.append({
            "Ferien": f["name"],
            "start": wochen["Wochenstart"].min(),
            "ende": wochen["Wochenende"].max(),
            "farbe": f.get("farbe", COLOR_HOLIDAY),
        })

ferien_df = pd.DataFrame(ferien_bereiche)
ferien_layer = alt.layer()
ferien_kw = []
for f in ferien:
    start_kw = int(f["start_kw"])
    ende_kw = int(f["end_kw"])

    if start_kw <= ende_kw:
        passende_ferien = ferien_df[ferien_df["Ferien"] == f["name"]]
        ferien_zeitraum = (
            f"{passende_ferien['start'].min():%d.%m.%Y} - "
            f"{passende_ferien['ende'].max():%d.%m.%Y}"
            if not passende_ferien.empty
            else f"KW {start_kw} - {ende_kw}"
        )
        ferien_kw.append({
            "Ferien": f["name"],
            "start_kw": start_kw - 0.5,
            "end_kw": ende_kw + 0.5,
            "Zeitraum": ferien_zeitraum,
            "KW": f"KW {start_kw} - {ende_kw}",
            "farbe": f.get("farbe", COLOR_HOLIDAY),
        })
    else:
        passende_ferien = ferien_df[ferien_df["Ferien"] == f["name"]]
        ferien_zeitraum = (
            f"{passende_ferien['start'].min():%d.%m.%Y} - "
            f"{passende_ferien['ende'].max():%d.%m.%Y}"
            if not passende_ferien.empty
            else f"KW {start_kw} - {ende_kw}"
        )
        ferien_kw.append({
            "Ferien": f["name"],
            "start_kw": start_kw - 0.5,
            "end_kw": 53.5,
            "Zeitraum": ferien_zeitraum,
            "KW": f"KW {start_kw} - 53",
            "farbe": f.get("farbe", COLOR_HOLIDAY),
        })
        ferien_kw.append({
            "Ferien": f["name"],
            "start_kw": 0.5,
            "end_kw": ende_kw + 0.5,
            "Zeitraum": ferien_zeitraum,
            "KW": f"KW 1 - {ende_kw}",
            "farbe": f.get("farbe", COLOR_HOLIDAY),
        })

ferien_kw_df = pd.DataFrame(ferien_kw)
if not ferien_kw_df.empty:
    ferien_domain = ferien_kw_df["Ferien"].drop_duplicates().tolist()
    ferien_range = (
        ferien_kw_df
        .drop_duplicates("Ferien")
        .set_index("Ferien")
        .loc[ferien_domain, "farbe"]
        .tolist()
    )
    ferien_layer = (
        alt.Chart(ferien_kw_df)
        .mark_rect(opacity=0.84, strokeOpacity=0.55, strokeWidth=1)
        .encode(
            x=alt.X("start_kw:Q"),
            x2=alt.X2("end_kw:Q"),
            color=alt.Color(
                "Ferien:N",
                scale=alt.Scale(
                    domain=ferien_domain,
                    range=ferien_range,
                ),
                legend=None,
            ),
            stroke=alt.Color(
                "Ferien:N",
                scale=alt.Scale(
                    domain=ferien_domain,
                    range=ferien_range,
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Ferien:N"),
                alt.Tooltip("Zeitraum:N"),
                alt.Tooltip("KW:N", title="Kalenderwochen"),
            ],
        )
    )

ferien_legend = ""
if not ferien_kw_df.empty:
    ferien_items = []
    for name, color in zip(ferien_domain, ferien_range):
        ferien_items.append(
            f'<span style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap;">'
            f'<span style="width:18px;height:10px;background:{color};border:1px solid {color};opacity:.45;display:inline-block;"></span>'
            f'{escape(str(name))}'
            f'</span>'
        )
    ferien_legend = "".join(ferien_items)

year_items = []
for idx, year in enumerate(sorted(pro_woche["Jahr"].dropna().astype(str).unique())):
    dash = "solid" if idx == 0 else "dashed"
    year_items.append(
        f'<span style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap;">'
        f'<span style="width:22px;border-top:3px {dash} {COLOR_VISITS};display:inline-block;"></span>'
        f'{escape(str(year))}'
        f'</span>'
    )

st.markdown(
    f"""
    <div style="display:flex;flex-wrap:wrap;gap:14px 20px;align-items:center;margin:.2rem 0 .6rem 0;font-size:.88rem;color:{TEXT};">
        <span style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap;">
            <span style="width:18px;height:10px;background:{COLOR_LOANS};opacity:.45;display:inline-block;"></span>
            Ausleihen
        </span>
        <span style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap;">
            <span style="width:22px;border-top:3px solid {COLOR_VISITS};display:inline-block;"></span>
            Zutritte
        </span>
        {''.join(year_items)}
        {ferien_legend}
    </div>
    """,
    unsafe_allow_html=True,
)

ausleihen_balken = (
    alt.Chart(pro_woche)
    .mark_bar(opacity=0.26, color=COLOR_LOANS)
    .encode(
        x=alt.X(
            "Kalenderwoche:Q",
            scale=alt.Scale(domain=[1, 53], nice=False),
            axis=alt.Axis(values=list(range(1, 54, 2)), labelAngle=0),
            title="Kalenderwoche",
        ),
        y=alt.Y(
            "Ausleihen:Q",
            title="Ausleihen",
            axis=alt.Axis(orient="right"),
        ),
        tooltip=[
            alt.Tooltip("Jahr:N"),
            alt.Tooltip("KW_Label:N", title="Kalenderwoche"),
            alt.Tooltip("Woche:N", title="Zeitraum"),
            alt.Tooltip("Ausleihen:Q", title="Ausleihen dieser Kunden"),
            alt.Tooltip("Ausleihen_pro_Zutritt:Q", title="Ausleihen / Zutritt"),
        ],
    )
)

zutritte_linie = (
    alt.Chart(pro_woche)
    .mark_line(color=COLOR_VISITS, point=True, strokeWidth=3)
    .encode(
        x=alt.X(
            "Kalenderwoche:Q",
            scale=alt.Scale(domain=[1, 53], nice=False),
            axis=alt.Axis(values=list(range(1, 54, 2)), labelAngle=0),
            title="Kalenderwoche",
        ),
        y=alt.Y(
            "Zutritte:Q",
            title="Zutritte",
        ),
        strokeDash=alt.StrokeDash(
            "Jahr:N",
            title="Jahr",
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("Jahr:N"),
            alt.Tooltip("KW_Label:N", title="Kalenderwoche"),
            alt.Tooltip("Woche:N", title="Zeitraum"),
            alt.Tooltip("Zutritte:Q", title="Zutritte"),
            alt.Tooltip("Ausleihen:Q", title="Ausleihen dieser Kunden"),
            alt.Tooltip("Ausleihen_pro_Zutritt:Q", title="Ausleihen / Zutritt"),
        ],
    )
)

zutritte_chart = (
    alt.layer(
        ferien_layer,
        ausleihen_balken,
        zutritte_linie,
    )
    .resolve_scale(
        color="independent",
        y="independent",
    )
    .properties(height=300)
)

st.altair_chart(zutritte_chart, use_container_width=True)

col1, col2 =st.columns([3,1])
if not pro_woche.empty:
    with col2:
        auswahl_optionen = pro_woche["Auswahl"].tolist()
        ausgewaehlte_woche = st.selectbox(
            "Woche auswählen",
            options=auswahl_optionen,
            index=len(auswahl_optionen) - 1,
            key="openlibrary_kw_auswahl",
        )

    woche_row = pro_woche.loc[
        pro_woche["Auswahl"] == ausgewaehlte_woche
    ].iloc[0]

    pro_tag = (
        df_open[
            (df_open["Jahr"] == woche_row["Jahr"])
            & (df_open["Kalenderwoche"] == woche_row["Kalenderwoche"])
        ]
        .groupby("Wochentag")
        .size()
        .reindex(reihenfolge)
        .fillna(0)
        .reset_index(name="Zutritte")
    )
    loans_tag = (
        df_loans_open[
            (df_loans_open["Jahr"] == woche_row["Jahr"])
            & (df_loans_open["Kalenderwoche"] == woche_row["Kalenderwoche"])
        ]
        .assign(Wochentag=lambda df: df["Ausleihdatum"].dt.day_name(locale="de_CH"))
        .groupby("Wochentag")
        .size()
        .reindex(reihenfolge)
        .fillna(0)
        .reset_index(name="Ausleihen")
        if not df_loans_open.empty
        else pd.DataFrame({
            "Wochentag": reihenfolge,
            "Ausleihen": [0] * len(reihenfolge),
        })
    )
    pro_tag = pro_tag.merge(
        loans_tag,
        on="Wochentag",
        how="left",
    )
    pro_tag["Ausleihen"] = pro_tag["Ausleihen"].fillna(0).astype(int)
    pro_tag_chart = pro_tag.melt(
        id_vars=["Wochentag"],
        value_vars=["Zutritte", "Ausleihen"],
        var_name="Kennzahl",
        value_name="Anzahl",
    )
    with col1:
        st.markdown(f"**Verteilung {woche_row['Woche']}**")

        tages_chart = (
            alt.Chart(pro_tag_chart)
            .mark_bar()
            .encode(
                x=alt.X(
                    "Wochentag:N",
                    sort=reihenfolge,
                    title="Wochentag",
                ),
                xOffset=alt.XOffset("Kennzahl:N"),
                y=alt.Y(
                    "Anzahl:Q",
                    title="Anzahl",
                ),
                color=alt.Color(
                    "Kennzahl:N",
                    scale=alt.Scale(
                        domain=["Zutritte", "Ausleihen"],
                        range=[COLOR_VISITS, COLOR_LOANS],
                    ),
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("Wochentag:N"),
                    alt.Tooltip("Kennzahl:N"),
                    alt.Tooltip("Anzahl:Q", title="Anzahl"),
                ],
            )
            .properties(height=260)
        )

        st.altair_chart(tages_chart, use_container_width=True)


# =====================================================

title_with_icon("Zutritte und Ausleihen nach Wochentag/Stunde", CALENDAR, icon_size=34, level="subheader")
steuerung_col1, steuerung_col2, steuerung_col3 = st.columns([1.8, 2.2, 1])

with steuerung_col1:
    darstellung_zutritte = st.radio(
        "Kennzahl",
        ["Gesamteintritte", "Durchschnitt", "% Anteil"],
        horizontal=True,
        key="openlibrary_zutritte_darstellung",
    )

with steuerung_col2:
    ausgewaehlte_tage = st.pills(
        "Wochentage",
        reihenfolge,
        selection_mode="multi",
        default=reihenfolge,
        key="openlibrary_wochentage_auswahl",
    )

with steuerung_col3:
    gesamtlinie_anzeigen = st.toggle(
        "Total über alle Wochentage anzeigen",
        value=True,
        key="openlibrary_stunden_gesamtlinie",
    )

if darstellung_zutritte == "% Anteil":
    st.caption(
        "Prozentwerte beziehen sich auf alle gefilterten Zutritte im angezeigten Bereich."
    )

# =====================================================
tab_zutritte, tab_ausleihen = st.tabs(["🚪 Zutritte", "📚 Ausleihen der Zutrittskunden"])

with tab_zutritte:
    # ZUTRITTE NACH STUNDE
    # =====================================================
    
    st.caption("🕒 Zutritte nach Stunde")
    
    df_stunden_basis = df_open[
        df_open["Wochentag"].isin(ausgewaehlte_tage)
        & df_open["Stunde"].between(oeffnung_start, oeffnung_ende)
    ].copy()
    
    stunden_index = pd.MultiIndex.from_product(
        [stunden_range, ausgewaehlte_tage],
        names=["Stunde", "Wochentag"],
    )
    
    if ausgewaehlte_tage:
        stunden = (
            df_stunden_basis
            .groupby(["Stunde", "Wochentag"])
            .size()
            .reindex(stunden_index, fill_value=0)
            .reset_index(name="Zutritte")
        )
    else:
        stunden = pd.DataFrame(columns=["Stunde", "Wochentag", "Zutritte"])
    
    stunden["Wochentag"] = pd.Categorical(
        stunden["Wochentag"],
        categories=reihenfolge,
        ordered=True
    )
    stunden["Stunden_label"] = stunden["Stunde"].map(lambda x: f"{x:02d}-{x + 1:02d}")
    stunden["Anzahl_Tage"] = stunden["Wochentag"].map(tage_anzahl).fillna(0).astype(int)
    stunden["Avg_Zutritte_pro_Tag"] = np.where(
        stunden["Anzahl_Tage"] > 0,
        stunden["Zutritte"] / stunden["Anzahl_Tage"],
        0,
    ).round(1)
    stunden_total = stunden["Zutritte"].sum()
    stunden["Anteil_Prozent"] = np.where(
        stunden_total > 0,
        stunden["Zutritte"] / stunden_total * 100,
        0,
    ).round(1)
    
    tage_im_filter = int(tage_anzahl.reindex(ausgewaehlte_tage).fillna(0).sum())
    stunden_gesamt = (
        df_stunden_basis
        .groupby("Stunde")
        .size()
        .reindex(stunden_range, fill_value=0)
        .reset_index(name="Zutritte")
    )
    stunden_gesamt["Stunden_label"] = stunden_gesamt["Stunde"].map(
        lambda x: f"{x:02d}-{x + 1:02d}"
    )
    stunden_gesamt["Anzahl_Tage"] = tage_im_filter
    stunden_gesamt["Avg_Zutritte_pro_Tag"] = np.where(
        tage_im_filter > 0,
        stunden_gesamt["Zutritte"] / tage_im_filter,
        0,
    ).round(1)
    stunden_gesamt_total = stunden_gesamt["Zutritte"].sum()
    stunden_gesamt["Anteil_Prozent"] = np.where(
        stunden_gesamt_total > 0,
        stunden_gesamt["Zutritte"] / stunden_gesamt_total * 100,
        0,
    ).round(1)
    stunden_gesamt["Serie"] = "Alle ausgewählten Tage"
    
    if darstellung_zutritte == "% Anteil":
        y_field = "Anteil_Prozent"
        y_title = "Anteil aller Zutritte (%)"
        y_tooltip = alt.Tooltip(
            "Anteil_Prozent:Q",
            title="Anteil aller Zutritte (%)",
            format=".1f",
        )
    elif darstellung_zutritte == "Durchschnitt":
        y_field = "Avg_Zutritte_pro_Tag"
        y_title = "Ø Zutritte je Stunde"
        y_tooltip = alt.Tooltip(
            "Avg_Zutritte_pro_Tag:Q",
            title="Ø je Stunde",
            format=".1f",
        )
    else:
        y_field = "Zutritte"
        y_title = "Gesamteintritte"
        y_tooltip = alt.Tooltip("Zutritte:Q", title="Gesamteintritte")
    
    wochentag_bars = (
        alt.Chart(stunden)
        .mark_bar()
        .encode(
            x=alt.X(
                "Stunden_label:N",
                sort=stunden_sort,
                title="Zeitfenster"
            ),
            xOffset=alt.XOffset(
                "Wochentag:N",
                sort=reihenfolge
            ),
            y=alt.Y(
                f"{y_field}:Q",
                title=y_title
            ),
            color=alt.Color(
                "Wochentag:N",
                sort=reihenfolge,
                scale=alt.Scale(
                    domain=reihenfolge,
                    range=COLOR_WEEKDAYS,
                ),
                legend=alt.Legend(orient="bottom")
            ),
            tooltip=[
                alt.Tooltip("Wochentag:N"),
                alt.Tooltip("Stunden_label:N", title="Zeitfenster"),
                alt.Tooltip("Zutritte:Q", title="Zutritte total"),
                alt.Tooltip("Anzahl_Tage:Q", title="Kalendertage"),
                y_tooltip,
            ]
        )
        .properties(height=320)
    )
    
    gesamt_linie = (
        alt.Chart(stunden_gesamt)
        .mark_line(color=TEXT, point=True, strokeWidth=3)
        .encode(
            x=alt.X(
                "Stunden_label:N",
                sort=stunden_sort,
                title="Zeitfenster",
            ),
            y=alt.Y(
                f"{y_field}:Q",
                title="Gesamt",
                axis=alt.Axis(orient="right"),
            ),
            tooltip=[
                alt.Tooltip("Serie:N"),
                alt.Tooltip("Stunden_label:N", title="Zeitfenster"),
                alt.Tooltip("Zutritte:Q", title="Zutritte total"),
                alt.Tooltip("Anzahl_Tage:Q", title="Kalendertage"),
                y_tooltip,
            ],
        )
    )
    
    chart = (
        alt.layer(
            wochentag_bars,
            gesamt_linie,
        ).resolve_scale(y="independent")
        if gesamtlinie_anzeigen
        else wochentag_bars
    )
    
    st.altair_chart(chart, use_container_width=True)
    

with tab_ausleihen:
    st.caption("📚 Ausleihen nach Stunde")
    
    df_ausleihen_stunden_basis = (
        df_loans_open[
            df_loans_open["Wochentag"].isin(ausgewaehlte_tage)
            & df_loans_open["Stunde"].between(oeffnung_start, oeffnung_ende)
        ].copy()
        if not df_loans_open.empty and "Stunde" in df_loans_open.columns
        else pd.DataFrame()
    )
    
    if df_ausleihen_stunden_basis.empty:
        st.info("Für die gewählten Filter sind keine Ausleihen der Zutrittskunden vorhanden.")
    else:
        ausleihen_stunden_index = pd.MultiIndex.from_product(
            [stunden_range, ausgewaehlte_tage],
            names=["Stunde", "Wochentag"],
        )
    
        ausleihen_stunden = (
            df_ausleihen_stunden_basis
            .groupby(["Stunde", "Wochentag"])
            .size()
            .reindex(ausleihen_stunden_index, fill_value=0)
            .reset_index(name="Ausleihen")
        )
        ausleihen_stunden["Wochentag"] = pd.Categorical(
            ausleihen_stunden["Wochentag"],
            categories=reihenfolge,
            ordered=True,
        )
        ausleihen_stunden["Stunden_label"] = ausleihen_stunden["Stunde"].map(
            lambda x: f"{x:02d}-{x + 1:02d}"
        )
        ausleihen_stunden["Anzahl_Tage"] = (
            ausleihen_stunden["Wochentag"]
            .map(tage_anzahl)
            .fillna(0)
            .astype(int)
        )
        ausleihen_stunden["Avg_Ausleihen_pro_Tag"] = np.where(
            ausleihen_stunden["Anzahl_Tage"] > 0,
            ausleihen_stunden["Ausleihen"] / ausleihen_stunden["Anzahl_Tage"],
            0,
        ).round(1)
        ausleihen_stunden_total = ausleihen_stunden["Ausleihen"].sum()
        ausleihen_stunden["Anteil_Prozent"] = np.where(
            ausleihen_stunden_total > 0,
            ausleihen_stunden["Ausleihen"] / ausleihen_stunden_total * 100,
            0,
        ).round(1)
    
        ausleihen_gesamt = (
            df_ausleihen_stunden_basis
            .groupby("Stunde")
            .size()
            .reindex(stunden_range, fill_value=0)
            .reset_index(name="Ausleihen")
        )
        ausleihen_gesamt["Stunden_label"] = ausleihen_gesamt["Stunde"].map(
            lambda x: f"{x:02d}-{x + 1:02d}"
        )
        ausleihen_gesamt["Anzahl_Tage"] = tage_im_filter
        ausleihen_gesamt["Avg_Ausleihen_pro_Tag"] = np.where(
            tage_im_filter > 0,
            ausleihen_gesamt["Ausleihen"] / tage_im_filter,
            0,
        ).round(1)
        ausleihen_gesamt_total = ausleihen_gesamt["Ausleihen"].sum()
        ausleihen_gesamt["Anteil_Prozent"] = np.where(
            ausleihen_gesamt_total > 0,
            ausleihen_gesamt["Ausleihen"] / ausleihen_gesamt_total * 100,
            0,
        ).round(1)
        ausleihen_gesamt["Serie"] = "Alle ausgewählten Tage"
    
        if darstellung_zutritte == "% Anteil":
            ausleihen_y_field = "Anteil_Prozent"
            ausleihen_y_title = "Anteil aller Ausleihen (%)"
            ausleihen_y_tooltip = alt.Tooltip(
                "Anteil_Prozent:Q",
                title="Anteil aller Ausleihen (%)",
                format=".1f",
            )
        elif darstellung_zutritte == "Durchschnitt":
            ausleihen_y_field = "Avg_Ausleihen_pro_Tag"
            ausleihen_y_title = "Ø Ausleihen je Stunde"
            ausleihen_y_tooltip = alt.Tooltip(
                "Avg_Ausleihen_pro_Tag:Q",
                title="Ø je Stunde",
                format=".1f",
            )
        else:
            ausleihen_y_field = "Ausleihen"
            ausleihen_y_title = "Gesamtausleihen"
            ausleihen_y_tooltip = alt.Tooltip("Ausleihen:Q", title="Gesamtausleihen")
    
        ausleihen_bars = (
            alt.Chart(ausleihen_stunden)
            .mark_bar()
            .encode(
                x=alt.X(
                    "Stunden_label:N",
                    sort=stunden_sort,
                    title="Zeitfenster",
                ),
                xOffset=alt.XOffset(
                    "Wochentag:N",
                    sort=reihenfolge,
                ),
                y=alt.Y(
                    f"{ausleihen_y_field}:Q",
                    title=ausleihen_y_title,
                ),
                color=alt.Color(
                    "Wochentag:N",
                    sort=reihenfolge,
                    scale=alt.Scale(
                        domain=reihenfolge,
                        range=COLOR_WEEKDAYS,
                    ),
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("Wochentag:N"),
                    alt.Tooltip("Stunden_label:N", title="Zeitfenster"),
                    alt.Tooltip("Ausleihen:Q", title="Ausleihen total"),
                    alt.Tooltip("Anzahl_Tage:Q", title="Kalendertage"),
                    ausleihen_y_tooltip,
                ],
            )
            .properties(height=300)
        )
    
        ausleihen_linie = (
            alt.Chart(ausleihen_gesamt)
            .mark_line(color=TEXT, point=True, strokeWidth=3)
            .encode(
                x=alt.X(
                    "Stunden_label:N",
                    sort=stunden_sort,
                    title="Zeitfenster",
                ),
                y=alt.Y(
                    f"{ausleihen_y_field}:Q",
                    title="Gesamt",
                    axis=alt.Axis(orient="right"),
                ),
                tooltip=[
                    alt.Tooltip("Serie:N"),
                    alt.Tooltip("Stunden_label:N", title="Zeitfenster"),
                    alt.Tooltip("Ausleihen:Q", title="Ausleihen total"),
                    alt.Tooltip("Anzahl_Tage:Q", title="Kalendertage"),
                    ausleihen_y_tooltip,
                ],
            )
        )
    
        ausleihen_chart = (
            alt.layer(
                ausleihen_bars,
                ausleihen_linie,
            ).resolve_scale(y="independent")
            if gesamtlinie_anzeigen
            else ausleihen_bars
        )
    
        st.altair_chart(ausleihen_chart, use_container_width=True)
    # =====================================================

with tab_zutritte:
    # ZUTRITTE NACH WOCHENTAG
    # =====================================================
    
    st.caption("📅 Zutritte nach Wochentag")
    
    
    tage = (
        df_open
        .groupby("Wochentag")
        .size()
        .reindex(reihenfolge)
        .fillna(0)
        .reset_index(name="Zutritte")
    )
    
    tage["Anzahl_Tage"] = tage["Wochentag"].map(tage_anzahl).fillna(0).astype(int)
    tage["Avg_Zutritte_pro_Tag"] = np.where(
        tage["Anzahl_Tage"] > 0,
        tage["Zutritte"] / tage["Anzahl_Tage"],
        0,
    ).round(1)
    tage_total = tage["Zutritte"].sum()
    tage["Anteil_Prozent"] = np.where(
        tage_total > 0,
        tage["Zutritte"] / tage_total * 100,
        0,
    ).round(1)
    
    if darstellung_zutritte == "% Anteil":
        tage_y_field = "Anteil_Prozent"
        tage_y_title = "Anteil der Zutritte (%)"
        tage_tooltip = alt.Tooltip("Anteil_Prozent:Q", title="Anteil (%)", format=".1f")
        tage["Anzeige_Label"] = tage["Anteil_Prozent"].map(lambda x: f"{x:.1f}%")
    elif darstellung_zutritte == "Durchschnitt":
        tage_y_field = "Avg_Zutritte_pro_Tag"
        tage_y_title = "Ø Zutritte / Tag"
        tage_tooltip = alt.Tooltip(
            "Avg_Zutritte_pro_Tag:Q",
            title="Ø Zutritte / Tag",
            format=".1f",
        )
        tage["Anzeige_Label"] = tage["Avg_Zutritte_pro_Tag"].map(lambda x: f"Ø {x:.1f}/Tag")
    else:
        tage_y_field = "Zutritte"
        tage_y_title = "Gesamteintritte"
        tage_tooltip = alt.Tooltip("Zutritte:Q", title="Gesamteintritte")
        tage["Anzeige_Label"] = tage["Zutritte"].map(lambda x: f"{int(x)}")
    
    bars = (
        alt.Chart(tage)
        .mark_bar(color=COLOR_VISITS)
        .encode(
            x=alt.X(
                "Wochentag:N",
                sort=reihenfolge
            ),
            y=alt.Y(
                f"{tage_y_field}:Q",
                title=tage_y_title,
            ),
            tooltip=[
                alt.Tooltip("Wochentag:N"),
                alt.Tooltip("Zutritte:Q", title="Zutritte total"),
                alt.Tooltip("Anzahl_Tage:Q", title="Kalendertage"),
                tage_tooltip,
            ]
        )
        .properties(height=300)
    )
    
    labels = (
        alt.Chart(tage)
        .mark_text(
            dy=-8,
            color=TEXT,
            fontWeight="bold",
        )
        .encode(
            x=alt.X(
                "Wochentag:N",
                sort=reihenfolge,
            ),
            y=f"{tage_y_field}:Q",
            text="Anzeige_Label:N",
        )
    )
    
    chart = alt.layer(
        bars,
        labels,
    )
    
    st.altair_chart(chart, use_container_width=True)
    

with tab_ausleihen:
    st.caption("📚 Ausleihen nach Wochentag")
    
    if df_loans_open.empty or "Wochentag" not in df_loans_open.columns:
        st.info("Für die gewählten Filter sind keine Ausleihen der Zutrittskunden vorhanden.")
    else:
        ausleihen_tage = (
            df_loans_open
            .groupby("Wochentag")
            .size()
            .reindex(reihenfolge)
            .fillna(0)
            .reset_index(name="Ausleihen")
        )
        ausleihen_tage["Anzahl_Tage"] = (
            ausleihen_tage["Wochentag"]
            .map(tage_anzahl)
            .fillna(0)
            .astype(int)
        )
        ausleihen_tage["Avg_Ausleihen_pro_Tag"] = np.where(
            ausleihen_tage["Anzahl_Tage"] > 0,
            ausleihen_tage["Ausleihen"] / ausleihen_tage["Anzahl_Tage"],
            0,
        ).round(1)
        ausleihen_tage_total = ausleihen_tage["Ausleihen"].sum()
        ausleihen_tage["Anteil_Prozent"] = np.where(
            ausleihen_tage_total > 0,
            ausleihen_tage["Ausleihen"] / ausleihen_tage_total * 100,
            0,
        ).round(1)
    
        if darstellung_zutritte == "% Anteil":
            ausleihen_tage_y_field = "Anteil_Prozent"
            ausleihen_tage_y_title = "Anteil der Ausleihen (%)"
            ausleihen_tage_tooltip = alt.Tooltip(
                "Anteil_Prozent:Q",
                title="Anteil (%)",
                format=".1f",
            )
            ausleihen_tage["Anzeige_Label"] = ausleihen_tage["Anteil_Prozent"].map(
                lambda x: f"{x:.1f}%"
            )
        elif darstellung_zutritte == "Durchschnitt":
            ausleihen_tage_y_field = "Avg_Ausleihen_pro_Tag"
            ausleihen_tage_y_title = "Ø Ausleihen / Tag"
            ausleihen_tage_tooltip = alt.Tooltip(
                "Avg_Ausleihen_pro_Tag:Q",
                title="Ø Ausleihen / Tag",
                format=".1f",
            )
            ausleihen_tage["Anzeige_Label"] = ausleihen_tage["Avg_Ausleihen_pro_Tag"].map(
                lambda x: f"Ø {x:.1f}/Tag"
            )
        else:
            ausleihen_tage_y_field = "Ausleihen"
            ausleihen_tage_y_title = "Gesamtausleihen"
            ausleihen_tage_tooltip = alt.Tooltip("Ausleihen:Q", title="Gesamtausleihen")
            ausleihen_tage["Anzeige_Label"] = ausleihen_tage["Ausleihen"].map(
                lambda x: f"{int(x)}"
            )
    
        ausleihen_tage_bars = (
            alt.Chart(ausleihen_tage)
            .mark_bar(color=COLOR_LOANS)
            .encode(
                x=alt.X(
                    "Wochentag:N",
                    sort=reihenfolge,
                ),
                y=alt.Y(
                    f"{ausleihen_tage_y_field}:Q",
                    title=ausleihen_tage_y_title,
                ),
                tooltip=[
                    alt.Tooltip("Wochentag:N"),
                    alt.Tooltip("Ausleihen:Q", title="Ausleihen total"),
                    alt.Tooltip("Anzahl_Tage:Q", title="Kalendertage"),
                    ausleihen_tage_tooltip,
                ],
            )
            .properties(height=300)
        )
    
        ausleihen_tage_labels = (
            alt.Chart(ausleihen_tage)
            .mark_text(
                dy=-8,
                color=TEXT,
                fontWeight="bold",
            )
            .encode(
                x=alt.X(
                    "Wochentag:N",
                    sort=reihenfolge,
                ),
                y=f"{ausleihen_tage_y_field}:Q",
                text="Anzeige_Label:N",
            )
        )
    
        st.altair_chart(
            alt.layer(
                ausleihen_tage_bars,
                ausleihen_tage_labels,
            ),
            use_container_width=True,
        )
    
    
    
