import streamlit as st
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
from utils import load_data, apply_filters
from filters import get_sidebar_filters

st.set_page_config(page_title="Ausleihen Analyse", page_icon="📊", layout="wide")
st.markdown("""
<style>
.main {
    padding-top: 1rem;
}

.block-container {
    padding-top: 2rem;
}

h1,h2,h3{
    color:#264653;
}

[data-testid="stMetric"]{
    border:1px solid #E6E6E6;
    border-radius:12px;
    padding:15px;
    background:white;
}

/* Sidebar etwas heller */
[data-testid="stSidebar"] {
    background-color: #fafafa;
}

/* Mehr Abstand zwischen Widgets */
[data-testid="stSidebar"] .stMultiSelect,
[data-testid="stSidebar"] .stDateInput {
    margin-bottom: .6rem;
}

/* Überschriften etwas kräftiger */
[data-testid="stSidebar"] h3 {
    margin-top: 0.8rem;
}

/* Toggle etwas Luft */
[data-testid="stSidebar"] .stToggle {
    padding-top: .4rem;
    padding-bottom: .4rem;
}
.filter-chip{
    display:inline-block;
    background:#eef3ff;
    color:#234;
    border:1px solid #c9d7ff;
    border-radius:18px;
    padding:5px 12px;
    margin:3px;
    font-size:0.88rem;
}

</style>
""", unsafe_allow_html=True)
st.title("📊 Detaillierte Ausleihen-Analyse")

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

# --- Filter (Identisch zur Startseite, muss hier wiederholt werden für Session State) ---
# ==========================
# Sidebar
# ==========================

st.sidebar.markdown("### 🔎 Filter")

# Zeitraum
st.sidebar.markdown("**📅 Zeitraum**")

date_range = None
# Datums-Filter (immer sichtbar)

if "Ausleihdatum" in df_ausleihe.columns:
    today=date.today()
    default_start= today -relativedelta(years=2)
    # Falls die Daten jünger sind als 2 Jahre
    min_date = df_ausleihe["Ausleihdatum"].min()
    max_date = df_ausleihe["Ausleihdatum"].max()
    default_start = max(default_start, min_date.date())
    date_range = None

    date_range = st.sidebar.date_input(
    "Ausleihdatum",
    value=(default_start, today),
    )

st.sidebar.divider()


def get_multiselect(label, column):
    if column not in df_ausleihe.columns:
        return []

    values = sorted(
        str(v)
        for v in df_ausleihe[column].dropna().unique()
        if str(v).strip() != ""
    )

    return st.sidebar.multiselect(
        label,
        options=values,
        default=values,
        placeholder=f"{label} auswählen..."
    )


st.sidebar.markdown("**🏢 Bibliothek**")
zweigstellen = get_multiselect("Zweigstelle", "Zweigstelle")

st.sidebar.markdown("**📚 Medien**")
medienarten = get_multiselect("Medienart", "Medienart")

st.sidebar.markdown("**👥 Benutzer**")
benutzergruppen = get_multiselect("Benutzergruppe", "Benutzergruppe")
alter = get_multiselect("Kategorie Alter", "Kategorie Alter")

st.sidebar.divider()

st.sidebar.markdown("### ⚙️ Optionen")

nur_erstausleihen = st.sidebar.toggle(
    "Nur Erstausleihen",
    value=False,
    help="Verlängerungen werden ausgeblendet."
)

filtered_df = apply_filters(
    df_ausleihe,
    date_range,
    zweigstellen,
    medienarten,
    benutzergruppen,
    alter,
    nur_erstausleihen=nur_erstausleihen
)
# -----------------------------
# Aktive Filter anzeigen
# -----------------------------

chips = []

if date_range:
    chips.append(
        f"📅 {date_range[0].strftime('%d.%m.%Y')} – {date_range[1].strftime('%d.%m.%Y')}"
    )

if len(zweigstellen) < df_ausleihe["Zweigstelle"].dropna().nunique():
    chips.append(f"🏢 {', '.join(zweigstellen)}")

if len(medienarten) < df_ausleihe["Medienart"].dropna().nunique():
    chips.append(f"📚 {', '.join(medienarten)}")

if len(benutzergruppen) < df_ausleihe["Benutzergruppe"].dropna().nunique():
    chips.append(f"👥 {', '.join(benutzergruppen)}")

if len(alter) < df_ausleihe["Kategorie Alter"].dropna().nunique():
    chips.append(f"🎂 {', '.join(alter)}")

if nur_erstausleihen:
    chips.append("✓ Nur Erstausleihen")

st.sidebar.divider()

st.sidebar.caption(f"📄 {len(filtered_df):,} Datensätze")

st.markdown("### 🔎 Aktive Filter")

if chips:
    html = ""

    for chip in chips:
        html += f"<span class='filter-chip'>{chip}</span>"

    st.markdown(html, unsafe_allow_html=True)
else:
    st.caption("Alle Daten")
# --- Charts ---
c1, c2 = st.columns(2)

with c1:
    st.subheader("Nach Medienart")
    if "Medienart" in filtered_df.columns:
        data = filtered_df["Medienart"].fillna("Unbekannt").value_counts().reset_index()
        data.columns = ["Medienart", "Anzahl"]
        st.bar_chart(data, x="Medienart", y="Anzahl")

with c2:
    st.subheader("Nach Wochentag")
    if "Ausleihdatum" in filtered_df.columns:
        wd_map = {"Monday": "Mo", "Tuesday": "Di", "Wednesday": "Mi", "Thursday": "Do", "Friday": "Fr", "Saturday": "Sa", "Sunday": "So"}
        data = (filtered_df.dropna(subset=["Ausleihdatum"])
                .assign(WD=lambda x: x["Ausleihdatum"].dt.day_name().map(wd_map))
                .groupby("WD").size().reindex(["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], fill_value=0)
                .reset_index(name="Anzahl"))
        st.bar_chart(data, x="WD", y="Anzahl")

# ------------------------------------------------------------
# Top 20 Medien mit Cover
# ------------------------------------------------------------

st.divider()
st.subheader("🏆 Top 20 ausgeliehene Medien")

# Erforderliche Felder prüfen
required_cols = {"NR Zugang", "MedienTitel", "MedienAutor", "URL_Cover"}

if required_cols.issubset(filtered_df.columns):
    # 1. Daten aggregieren
    # Wir gruppieren und nehmen das erste vorkommende Cover (da es pro Medien-ID gleich sein sollte)
    top_media = (
        filtered_df
        .groupby(["NR Zugang", "MedienTitel", "MedienAutor", "URL_Cover"], dropna=False)
        .size()
        .reset_index(name="Ausleihen")
        .sort_values("Ausleihen", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )

    # 2. Spalte für die Bild-Anzeige vorbereiten (Markdown Syntax)
    # Streamlit rendert ![Alt Text](URL) automatisch als Bild, wenn column_config genutzt wird
    # Wir erstellen eine helper-spalte, die nur das Markdown enthält
    def create_image_markdown(url):
        if pd.notna(url) and str(url).strip() != "":
            return f"![Cover]({url})"
        return "Kein Bild"

    top_media["Cover_Vorschau"] = top_media["URL_Cover"].apply(create_image_markdown)

    # 3. Anzeige konfigurieren
    # Wir wählen die Spalten in der gewünschten Reihenfolge
    display_columns = ["Cover_Vorschau", "MedienTitel", "MedienAutor", "Ausleihen"]

    st.dataframe(
        top_media[display_columns],
        width="stretch",
        hide_index=True,
        column_config={
            "Cover_Vorschau": st.column_config.TextColumn(
                "Cover",
                help="Buchcover",
                width="small"
            ),
            "MedienTitel": st.column_config.TextColumn(
                "Titel",
                width="medium"
            ),
            "MedienAutor": st.column_config.TextColumn(
                "Autor",
                width="medium"
            ),
            "Ausleihen": st.column_config.NumberColumn(
                "Ausleihen",
                format="%d"
            )
        }
    )
else:
    missing = required_cols - set(filtered_df.columns)
    if "URL_Cover" in missing:
        st.warning("Feld 'URL_Cover' nicht gefunden. Anzeige ohne Bilder.")
        # Fallback ohne Bilder
        if {"NR Zugang", "MedienTitel", "MedienAutor"}.issubset(filtered_df.columns):
            top_simple = (
                filtered_df.groupby(["NR Zugang", "MedienTitel", "MedienAutor"], dropna=False)
                .size().reset_index(name="Ausleihen")
                .sort_values("Ausleihen", ascending=False).head(20)
            )
            st.dataframe(top_simple, hide_index=True, width="stretch")
    else:
        st.error(f"Fehlende Felder für diese Ansicht: {missing}")
