import streamlit as st
import pandas as pd
from utils import load_data, apply_filters

st.set_page_config(page_title="Medien Analyse", page_icon="📚", layout="wide")
st.title("Medienbestand und Top-Listen")

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

# --- Filter (Identisch zur Startseite, muss hier wiederholt werden für Session State) ---
st.sidebar.header("Filter")
date_range = None
if "Ausleihdatum" in df_ausleihe.columns:
    min_date = df_ausleihe["Ausleihdatum"].min()
    max_date = df_ausleihe["Ausleihdatum"].max()
    if pd.notna(min_date) and pd.notna(max_date):
        date_range = st.sidebar.date_input("Ausleihdatum", value=(min_date.date(), max_date.date()))

def get_multiselect(label, column):
    if column not in df_ausleihe.columns: return []
    values = sorted([str(v) for v in df_ausleihe[column].dropna().unique() if str(v).strip() != ""])
    return st.sidebar.multiselect(label, options=values, default=values)
# --- NEUE CHECKBOX ---
nur_erstausleihen = st.sidebar.checkbox(
    "Nur Erstausleihen",
    value=False,
    help="Blendet Verlängerungen aus (zeigt nur Datensätze mit Verlängerung_Anz = 0)."
)
filtered_df = apply_filters(df_ausleihe, date_range, 
    get_multiselect("Zweigstelle", "Zweigstelle"),
    get_multiselect("Medienart", "Medienart"),
    get_multiselect("Benutzergruppe", "Benutzergruppe"),
    get_multiselect("Kategorie Alter", "Kategorie Alter"),
    nur_erstausleihen=nur_erstausleihen
)


st.subheader("Top 20 ausgeliehene Medien")

required_cols = {"NR Zugang", "MedienTitel", "MedienAutor", "URL_Cover"}

if required_cols.issubset(filtered_df.columns):

    top_media = (
        filtered_df
        .groupby(["NR Zugang", "MedienTitel", "MedienAutor", "URL_Cover"], dropna=False)
        .size()
        .reset_index(name="Ausleihen")
        .sort_values("Ausleihen", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )

    # =========================
    # 🎨 FIXED COVER STYLE
    # =========================
    st.markdown("""
    <style>
    .poster {
        width: 100%;
        height: 180px;
        object-fit: cover;
        border-radius: 10px;
    }
    .poster:hover {
        transform: scale(1.03);
        transition: 0.2s;
    }
    .card-title {
        font-size: 18px;
        font-weight: 700;
        margin-top: 8px;
        line-heigth: 1.2;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .card-author {
        font-size: 14px;
        opacity: 0.75;
        margin-top: 2px;
    }
    .rank {
        font-size: 18px;
        font-weight: 700;
    }
    /* 📊 Metric Text (Streamlit metric override light) */
    div[data-testid="metric-container"] {
        font-size: 16px;
    }

    div[data-testid="metric-container"] > div {
        font-size: 14px;
    }
    </style>
    """, unsafe_allow_html=True)

    # =========================
    # GRID
    # =========================
    cols_per_row = 5

    for start in range(0, len(top_media), cols_per_row):
        row_items = top_media.iloc[start:start + cols_per_row]
        cols = st.columns(cols_per_row)

        for col, (_, row) in zip(cols, row_items.iterrows()):

            with col:
                st.markdown(f"**#{row.name + 1}**")

                if pd.notna(row["URL_Cover"]) and str(row["URL_Cover"]).strip():
                    st.markdown(
                        f"""
                        <img src="{row['URL_Cover']}" class="poster">
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown("""
                    <div class="poster" style="
                        display:flex;
                        align-items:center;
                        justify-content:center;
                        background:#222;
                        color:#aaa;
                        border-radius:10px;
                    ">📕</div>
                    """, unsafe_allow_html=True)

                st.markdown(f"""
                <div class="card-title">{row['MedienTitel']}</div>
                <div class="card-author">{row['MedienAutor']}</div>
                """, unsafe_allow_html=True)

                st.metric("Ausleihen", int(row["Ausleihen"]))