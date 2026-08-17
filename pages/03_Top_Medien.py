import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import altair as alt
from src.utils import load_data, normalize_media_id
from src.filters import get_sidebar_filters, build_filtered_data
from components.ui import show_new_acquisition_detail

st.set_page_config(page_title="Top Medien", page_icon="🏆", layout="wide")

st.title("🏆 Top Medien")


# Prüfen, ob Daten geladen wurden
if 'data' not in st.session_state or st.session_state['data'] is None:
    st.error("Keine Daten geladen. Bitte starten Sie das Dashboard über die Startseite.")
    st.stop()

data = st.session_state['data']
df_users = data.get("users")
df_ausleihe = data.get("loans") 
df_katalog = data.get('catalog')

if df_users is None:
    st.warning("Keine Nutzerdaten verfügbar.")
    st.stop()

filtered_users, filtered_loans, filter_state = get_sidebar_filters(
    df_users=df_users,
    df_extra=df_ausleihe,
    df_catalog=df_katalog,
    prefix="top_medien",

    enable_date_filter=True,
    enable_first_loan_toggle=True,

    extra_filters_config=[
        {
            "col": "Zweigstelle",
            "label": "Zweigstelle",
        },

    ],

    catalog_filters_config=[
        {"col": "Lieferant", "label": "Lieferant", "type": "multiselect"},
        {"col": "Preis", "label": "Preis", "type":"range", "currency":True, "step":5.0},
        {"col": "Datum der Aufnahme", "label": "Neuanschaffung", "type": "date_preset"},
        {"col": "Sprache(1)", "label": "Sprache", "type": "multiselect"},
        {"col": "Medienart", "label": "Medienart", "type": "multiselect"},
        {"col": "Kategorie Alter", "label": "Lesealter",  "type": "multiselect"},
        {"col": "Standort(1)", "label": "Standort", "type": "multiselect" },
        #{"col": "katalogisiert durch", "label": "Katalogisiert durch"},
    ],
    expander_defaults={
        "target": False,
        "loans": True,
        "catalog": True,
    },
)
filtered_data = build_filtered_data(
    data=data,
    filtered_users=filtered_users,
    filtered_loans=filtered_loans,
    filter_state=filter_state,
)

df_users = filtered_data['users']
df_ausleihe = filtered_data['loans']
df_ausleihe_no_date = filtered_data['loans_no_date']
df_katalog = filtered_data['books']
df_books_used=filtered_data['books_used']




# Auswahl Anzahl Top Medien
col1,col2=st.columns([5,1])
with col1:
    st.header("Top-Ausleihen-Listen")
with col2:
    optionen = [3,5,10,20,50,100, "Alle", "Benutzerdefiniert"]
    auswahl = st.selectbox('Anzahl Medien', optionen, index=3)

    # Medien ohne Ausleihe
    auch_ohne_ausleihe = st.toggle(
        "Medien ohne Ausleihe anzeigen",
        value=False,
        help= (
            "Zeigt auch Medien aus dem gefilterten Katalog, "
            "die im gewählten Zeitraum nicht ausgeliehen wurden."
        )
    )

    max_medien = (len(df_katalog) if auch_ohne_ausleihe else df_ausleihe['NR Zugang'].nunique())

    if auswahl == 'Benutzerdefiniert':
        st.caption(f"Verfügbar: {max_medien} Medien")
        anzahl = st.number_input(
            "Anzahl eingeben",
            min_value=1,
            value=min(5, max_medien),
            step=1
        )

        anzahl = min(int(anzahl), max_medien)

    elif auswahl == "Alle":
        anzahl= max_medien
    else:
        anzahl= min(int(auswahl), max_medien)

st.caption(
    "Die Ausleihzahlen berücksichtigen den gewählten Ausleihe-Zeitraum "
    "und den Filter «Ohne Verlängerungen»."
)

required_cols = {"NR Zugang", "MedienTitel", "MedienAutor", "URL_Cover"}

if auch_ohne_ausleihe:
    # Katalog als Basis
    required_catalog_cols = {
        "NR Zugang",
        "Titel",
        "Verfasser I(1)",
        "URL_Cover",
        "Reihe(1)",
        "Band"
    }
    if required_catalog_cols.issubset(df_katalog.columns):
        # Nur Ausleihen der aktuell gefilterten Medien
        katalog_basis = df_katalog.copy()
        katalog_basis["_NR Zugang Match"] = katalog_basis["NR Zugang"].apply(
            normalize_media_id
        )

        katalog_nr = set(
            katalog_basis["_NR Zugang Match"]
            .dropna()
            .unique()
        )

        loans_fuer_katalog = df_ausleihe.copy()
        loans_fuer_katalog["_NR Zugang Match"] = loans_fuer_katalog["NR Zugang"].apply(
            normalize_media_id
        )

        loans_fuer_katalog = loans_fuer_katalog[
            loans_fuer_katalog["_NR Zugang Match"]
            .isin(katalog_nr)
        ].copy()

        # Anzahl Ausleihen pro Medium berechnen
        ausleih_counts = (
            loans_fuer_katalog
            .groupby("_NR Zugang Match")
            .size()
            .reset_index(name="Ausleihen")
        )
        # Falls bereits "Ausleihen" enthält: alte Spalten entfernen
        if "Ausleihen" in katalog_basis.columns:
            katalog_basis = katalog_basis.drop(
                columns =['Ausleihen']
            ).copy()

        # Katalog + Ausleihzahlen verbinden
        top_media = katalog_basis.merge(
            ausleih_counts,
            on="_NR Zugang Match",
            how="left"
        )
        # Spaltennamen vereinheitlichen
        top_media = top_media.rename(
            columns={
                "Titel":"MedienTitel",
                "Verfasser I(1)": "MedienAutor",
            }
        )
        # Medien ohne Ausleihen bekommen 0
        top_media['Ausleihen']=(
            top_media["Ausleihen"]
            .fillna(0)
            .astype(int)
        )
        # Nach Ausleihen sortieren
        top_media= (
            top_media
            .sort_values(
                "Ausleihen",
                ascending=False
            )
            .head(anzahl)
            .reset_index(drop=True)
        )
    else:
        st.warning("Die benötigten Katalogspalten für die Medienanzeige fehlen.")
        st.write(df_katalog.columns)
        
else:
    if required_cols.issubset(df_ausleihe.columns):
        top_media = (
            df_ausleihe
            .groupby(["NR Zugang", "MedienTitel", "MedienAutor", "URL_Cover", "Reihe(1)","Band"], dropna=False)
            .size()
            .reset_index(name="Ausleihen")
            .sort_values("Ausleihen", ascending=False)
            .head(anzahl)
            .reset_index(drop=True)
        )


st.subheader(f"Top {anzahl} ausgeliehene Medien")


# =========================
# 🎨 FIXED COVER STYLE
# =========================
st.markdown("""
<style>
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
    margin-bottom: 0.8rem;
}
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
    text-align: center;
}

.card-author {
    font-size: 14px;
    opacity: 0.75;
    margin-top: 2px;
    text-align: center;
}
.card-count {
    margin-top: 8px;
    font-size: 15px;
    font-weight: 600;
    color: #444;
    text-align: right;
}
.card-series {
    margin-top: 4px;
    font-size: 0.8rem;
    color: #888;
    font-style: italic;
    text-align:center;
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
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div class="card-header">
                        <span><strong>#{row.name + 1}</strong></span>
                        <div class="card-count">📖 {int(row['Ausleihen'])} Ausleihen</div>
                    </div>
                    """, unsafe_allow_html=True
                    )


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

                author= row['MedienAutor']
                author= author.strip() if isinstance(author,str) else ""
                reihe = row.get('Reihe(1)', "")
                band =row.get("Band", "")
                reihe = reihe.strip() if isinstance(reihe,str) else ""
                band = str(band).strip() if pd.notna(band) else ""
                if reihe:
                    if band:
                        serie = f"{reihe} - Band {band}"
                    else:
                        serie = reihe
                else:
                    serie = "-"

                st.markdown(f"""
                <div class="card-title">{row['MedienTitel']}</div>
                <div class="card-author">{author if author else "-"}</div>
                <div class="card-series">{serie}</div>                    
                """, unsafe_allow_html=True)
