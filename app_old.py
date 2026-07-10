import json
from pathlib import Path

import pandas as pd
import streamlit as st


CACHE_FILE = Path("data/raw/filemaker_records.json")


st.set_page_config(
    page_title="Ausleihen Dashboard",
    page_icon="📚",
    layout="wide"
)


def parse_date(series):
    return pd.to_datetime(series, errors="coerce", format="%m/%d/%Y")


def parse_datetime(series):
    return pd.to_datetime(series, errors="coerce", format="%m/%d/%Y %H:%M:%S")


@st.cache_data
def load_data():
    if not CACHE_FILE.exists():
        return None, None

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    records = cache.get("records", [])

    rows = []
    for record in records:
        row = record.get("fieldData", {}).copy()
        row["recordId"] = record.get("recordId")
        row["modId"] = record.get("modId")
        rows.append(row)

    df = pd.DataFrame(rows)

    if df.empty:
        return cache, df

    # Datumsfelder aus deinem Beispiel
    date_columns = [
        "Ausleihdatum",
        "Rückgabedatum",
        "Ausleihe bis",
        "Mahndatum 0",
        "Mahndatum 1",
        "Mahndatum 2",
        "Mahndatum 3",
        "RG_Datum",
    ]

    for col in date_columns:
        if col in df.columns:
            df[col] = parse_date(df[col])

    if "erstellt" in df.columns:
        df["erstellt"] = parse_datetime(df["erstellt"])

    if "geändert" in df.columns:
        df["geändert"] = parse_datetime(df["geändert"])

    # Numerische Felder
    numeric_columns = [
        "NR Zugang",
        "Verlängerung_Anz",
        "Transaktionstyp(1)",
        "Transaktionstyp(2)",
        "Anz_Exemplare",
        "Stat_Ausl_inkl_Verl",
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return cache, df


cache, df = load_data()


st.title("📚 Bibliothek Seengen 📚 Dashboard")
st.caption("Erstes Dashboard auf Basis des lokalen FileMaker-Caches")

if df is None:
    st.error("Keine Cache-Datei gefunden. Bitte zuerst fetch_filemaker.py ausführen.")
    st.stop()

if df.empty:
    st.warning("Die Cache-Datei enthält keine Datensätze.")
    st.stop()

cached_at = cache.get("cached_at", "unbekannt")
record_count = cache.get("record_count", len(df))

st.caption(f"Letzte Cache-Aktualisierung: {cached_at} · Datensätze: {record_count:,}".replace(",", "'"))

# ------------------------------------------------------------
# Sidebar Filter
# ------------------------------------------------------------

st.sidebar.header("Filter")

if "Ausleihdatum" in df.columns:
    min_date = df["Ausleihdatum"].min()
    max_date = df["Ausleihdatum"].max()

    if pd.notna(min_date) and pd.notna(max_date):
        date_range = st.sidebar.date_input(
            "Ausleihdatum",
            value=(min_date.date(), max_date.date()),
            min_value=min_date.date(),
            max_value=max_date.date(),
        )
    else:
        date_range = None
else:
    date_range = None


def multiselect_filter(label, column):
    if column not in df.columns:
        return []

    values = sorted([
        str(value)
        for value in df[column].dropna().unique()
        if str(value).strip() != ""
    ])

    return st.sidebar.multiselect(
        label,
        options=values,
        default=values
    )


selected_zweigstellen = multiselect_filter("Zweigstelle", "Zweigstelle")
selected_medienarten = multiselect_filter("Medienart", "Medienart")
selected_benutzergruppen = multiselect_filter("Benutzergruppe", "Benutzergruppe")
selected_kategorie_alter = multiselect_filter("Kategorie Alter", "Kategorie Alter")


filtered = df.copy()

if date_range and len(date_range) == 2 and "Ausleihdatum" in filtered.columns:
    start_date = pd.to_datetime(date_range[0])
    end_date = pd.to_datetime(date_range[1])
    filtered = filtered[
        (filtered["Ausleihdatum"] >= start_date)
        & (filtered["Ausleihdatum"] <= end_date)
    ]

if selected_zweigstellen and "Zweigstelle" in filtered.columns:
    filtered = filtered[filtered["Zweigstelle"].astype(str).isin(selected_zweigstellen)]

if selected_medienarten and "Medienart" in filtered.columns:
    filtered = filtered[filtered["Medienart"].astype(str).isin(selected_medienarten)]

if selected_benutzergruppen and "Benutzergruppe" in filtered.columns:
    filtered = filtered[filtered["Benutzergruppe"].astype(str).isin(selected_benutzergruppen)]

if selected_kategorie_alter and "Kategorie Alter" in filtered.columns:
    filtered = filtered[filtered["Kategorie Alter"].astype(str).isin(selected_kategorie_alter)]


# ------------------------------------------------------------
# KPIs
# ------------------------------------------------------------

st.subheader("Kennzahlen")

total_loans = len(filtered)

if "Stat_Ausl_inkl_Verl" in filtered.columns:
    total_loans_incl_renewals = int(filtered["Stat_Ausl_inkl_Verl"].sum())
else:
    total_loans_incl_renewals = total_loans

if "Ausleihperson" in filtered.columns:
    active_users = filtered["Ausleihperson"].nunique()
else:
    active_users = 0

if "NR Zugang" in filtered.columns:
    unique_media = filtered["NR Zugang"].nunique()
else:
    unique_media = 0

if "Rückgabedatum" in filtered.columns:
    open_loans = filtered["Rückgabedatum"].isna().sum()
else:
    open_loans = 0

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Ausleihe-Datensätze", f"{total_loans:,}".replace(",", "'"))
col2.metric("Ausleihen inkl. Verlängerungen", f"{total_loans_incl_renewals:,}".replace(",", "'"))
col3.metric("Aktive Kund:innen", f"{active_users:,}".replace(",", "'"))
col4.metric("Einzelne Medien", f"{unique_media:,}".replace(",", "'"))
col5.metric("Offene Ausleihen", f"{open_loans:,}".replace(",", "'"))

st.divider()


# ------------------------------------------------------------
# Zeitverlauf
# ------------------------------------------------------------

if "Ausleihdatum" in filtered.columns:
    st.subheader("Ausleihen im Zeitverlauf")

    trend = (
        filtered
        .dropna(subset=["Ausleihdatum"])
        .assign(Monat=lambda x: x["Ausleihdatum"].dt.to_period("M").dt.to_timestamp())
        .groupby("Monat")
        .size()
        .reset_index(name="Ausleihen")
        .sort_values("Monat")
    )

    if not trend.empty:
        st.line_chart(trend, x="Monat", y="Ausleihen", width="stretch")
    else:
        st.info("Für den gewählten Zeitraum gibt es keine Ausleihdaten.")


# ------------------------------------------------------------
# Diagramme nebeneinander
# ------------------------------------------------------------

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("Ausleihen nach Medienart")

    if "Medienart" in filtered.columns:
        medienart_counts = (
            filtered["Medienart"]
            .fillna("Unbekannt")
            .replace("", "Unbekannt")
            .value_counts()
            .head(15)
            .reset_index()
        )
        medienart_counts.columns = ["Medienart", "Ausleihen"]

        st.bar_chart(medienart_counts, x="Medienart", y="Ausleihen", width="stretch")
    else:
        st.info("Feld 'Medienart' nicht gefunden.")

with chart_col2:
    st.subheader("Ausleihen nach Zweigstelle")

    if "Zweigstelle" in filtered.columns:
        zweigstelle_counts = (
            filtered["Zweigstelle"]
            .fillna("Unbekannt")
            .replace("", "Unbekannt")
            .value_counts()
            .reset_index()
        )
        zweigstelle_counts.columns = ["Zweigstelle", "Ausleihen"]

        st.bar_chart(zweigstelle_counts, x="Zweigstelle", y="Ausleihen", width="stretch")
    else:
        st.info("Feld 'Zweigstelle' nicht gefunden.")


chart_col3, chart_col4 = st.columns(2)

with chart_col3:
    st.subheader("Ausleihen nach Benutzergruppe")

    if "Benutzergruppe" in filtered.columns:
        usergroup_counts = (
            filtered["Benutzergruppe"]
            .fillna("Unbekannt")
            .replace("", "Unbekannt")
            .value_counts()
            .reset_index()
        )
        usergroup_counts.columns = ["Benutzergruppe", "Ausleihen"]

        st.bar_chart(usergroup_counts, x="Benutzergruppe", y="Ausleihen", width="stretch")
    else:
        st.info("Feld 'Benutzergruppe' nicht gefunden.")

with chart_col4:
    st.subheader("Ausleihen nach Wochentag")

    if "Ausleihdatum" in filtered.columns:
        weekday_order = [
            "Montag",
            "Dienstag",
            "Mittwoch",
            "Donnerstag",
            "Freitag",
            "Samstag",
            "Sonntag",
        ]

        weekday_map = {
            "Monday": "Montag",
            "Tuesday": "Dienstag",
            "Wednesday": "Mittwoch",
            "Thursday": "Donnerstag",
            "Friday": "Freitag",
            "Saturday": "Samstag",
            "Sunday": "Sonntag",
        }

        weekday_counts = (
            filtered
            .dropna(subset=["Ausleihdatum"])
            .assign(Wochentag=lambda x: x["Ausleihdatum"].dt.day_name().map(weekday_map))
            .groupby("Wochentag")
            .size()
            .reindex(weekday_order, fill_value=0)
            .reset_index(name="Ausleihen")
        )

        st.bar_chart(weekday_counts, x="Wochentag", y="Ausleihen", width="stretch")
    else:
        st.info("Feld 'Ausleihdatum' nicht gefunden.")


# ------------------------------------------------------------
# Top Listen
# ------------------------------------------------------------

st.divider()
st.subheader("Top-Listen")

top_col1, top_col2 = st.columns(2)

with top_col1:
    st.markdown("**Top 20 Medien nach Ausleihen**")

    required_cols = {"NR Zugang", "MedienTitel", "MedienAutor"}
    if required_cols.issubset(filtered.columns):
        top_media = (
            filtered
            .groupby(["NR Zugang", "MedienTitel", "MedienAutor"], dropna=False)
            .size()
            .reset_index(name="Ausleihen")
            .sort_values("Ausleihen", ascending=False)
            .head(20)
        )

        st.dataframe(top_media, width="stretch", hide_index=True)
    else:
        st.info("Für diese Liste fehlen Felder wie 'NR Zugang', 'MedienTitel' oder 'MedienAutor'.")

with top_col2:
    st.markdown("**Aktivste Kund:innen, anonymisiert**")

    if "Ausleihperson" in filtered.columns:
        top_users = (
            filtered
            .groupby("Ausleihperson")
            .size()
            .reset_index(name="Ausleihen")
            .sort_values("Ausleihen", ascending=False)
            .head(20)
        )

        top_users["Ausleihperson"] = top_users["Ausleihperson"].astype(str)

        st.dataframe(top_users, width="stretch", hide_index=True)
    else:
        st.info("Feld 'Ausleihperson' nicht gefunden.")


# ------------------------------------------------------------
# Rohdaten
# ------------------------------------------------------------

st.divider()

with st.expander("Gefilterte Rohdaten anzeigen"):
    st.dataframe(filtered, width="stretch")

st.caption("Hinweis: Dieses Dashboard verwendet lokale Cache-Daten aus FileMaker.")