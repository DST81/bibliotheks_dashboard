import streamlit as st
import pandas as pd
from html import escape
from src.utils import normalize_media_id
from src.filters import get_sidebar_filters, build_filtered_data
from src.pdf_report import build_top_media_pdf
from src.report_helpers import format_filter_value
from src.theme import (
    PRIMARY,
    TEXT,
    MUTED,
    BORDER,
    COLOR_PLACEHOLDER_BG,
    COLOR_PLACEHOLDER_TEXT,
)
from components.icons import TOP
from components.ui import title_with_icon

st.set_page_config(page_title="Top Medien", page_icon="assets/top_medien.svg", layout="wide")

# Prüfen, ob Daten geladen wurden
if 'data' not in st.session_state or st.session_state['data'] is None:
    st.error("Keine Daten geladen. Bitte starten Sie das Dashboard über die Startseite.")
    st.stop()

data = st.session_state['data']
df_users = data.get("users")
df_ausleihe = data.get("loans") 
df_katalog = data.get('catalog')
df_katalog_raw = df_katalog.copy() if df_katalog is not None else pd.DataFrame()
if df_ausleihe is None:
    df_ausleihe = pd.DataFrame()
if df_katalog is None:
    df_katalog = pd.DataFrame()

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
            "col": "Zweigstelle_loan",
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
if df_ausleihe is None:
    df_ausleihe = pd.DataFrame()
if df_katalog is None:
    df_katalog = pd.DataFrame()




# Auswahl Anzahl Top Medien
col1,col2=st.columns([3,2])
with col1:
    title_placeholder = st.empty()

    with title_placeholder:
        title_with_icon(
            "Top Medien",
            TOP
        )
with col2:
    c1, c2 = st.columns(2)
    with c2:
        optionen = [3,5,10,20,50,100, "Alle", "Benutzerdefiniert"]
        auswahl = st.selectbox('Anzahl Medien', optionen, index=3)
    with c1:
        # Medien ohne Ausleihe
        auch_ohne_ausleihe = st.toggle(
            "Medien ohne Ausleihe anzeigen",
            value=False,
            help= (
                "Zeigt auch Medien aus dem gefilterten Katalog, "
                "die im gewählten Zeitraum nicht ausgeliehen wurden."
            )
        )

    if auch_ohne_ausleihe:
        max_medien = len(df_katalog)
    elif "NR Zugang" in df_ausleihe.columns:
        max_medien = df_ausleihe["NR Zugang"].nunique()
    else:
        max_medien = 0

    if max_medien <= 0:
        st.info("Keine Medien fuer die aktuelle Auswahl verfuegbar.")
        st.stop()

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
    with title_placeholder:
        title_with_icon(
            f"Top {anzahl} Medien",
            TOP
        )

required_cols = {"NR Zugang", "MedienTitel", "MedienAutor", "URL_Cover"}
top_media = pd.DataFrame()

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

        if "NR Zugang" in df_ausleihe.columns:
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
        else:
            ausleih_counts = pd.DataFrame(columns=["_NR Zugang Match", "Ausleihen"])
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
        st.stop()
        
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
    else:
        st.warning("Die benoetigten Ausleihspalten fuer die Medienanzeige fehlen.")
        st.write(df_ausleihe.columns)
        st.stop()

if top_media.empty:
    st.info("Keine Medien fuer die aktuelle Auswahl verfuegbar.")
    st.stop()

col1, col2 = st.columns([4,1])
with col1:

    verlaengerungs_text = (
        "OHNE Verlängerung"
        if filter_state.get("first_loan_only", False)
        else "inkl. Verlängerungen"
    )
    st.caption(
        f"Ausleihzahlen im gewählten Zeitraum · {verlaengerungs_text}"
    )
with col2:
    date_range = filter_state.get("date_range")

    if (
        isinstance(date_range, tuple)
        and len(date_range) == 2
    ):
        zeitraum_text = (
            f"{date_range[0].strftime('%d.%m.%Y')} - "
            f"{date_range[1].strftime('%d.%m.%Y')}"
        )
    else:
        zeitraum_text = "gewählter Zeitraum"


    verlaengerungs_text = (
        "ohne Verlängerungen"
        if filter_state.get("first_loan_only", False)
        else "inkl. Verlängerungen"
    )

    catalog_filters = filter_state.get("catalog_filters", {})
    pdf_filter_columns = [
        ("Medienart", "Medienart", {}),
        ("Lesealter", "Kategorie Alter", {}),
        ("Standort", "Standort(1)", {}),
        ("Sprache", "Sprache(1)", {}),
        ("Lieferant", "Lieferant", {}),
        ("Preis", "Preis", {"currency": True}),
        ("Neuanschaffung", "Datum der Aufnahme", {}),
    ]

    def is_active_catalog_filter(col, value):
        if value in (None, "", []):
            return False

        if isinstance(value, str):
            return value not in ("Alle", "Alle Medien")

        if isinstance(value, list):
            if not value:
                return False
            if col in df_katalog_raw.columns:
                all_values = (
                    df_katalog_raw[col]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .loc[lambda s: s != ""]
                    .unique()
                    .tolist()
                )
                if set(map(str, value)) == set(map(str, all_values)):
                    return False
            return True

        if isinstance(value, tuple) and len(value) == 2:
            if col in df_katalog_raw.columns:
                numeric = pd.to_numeric(df_katalog_raw[col], errors="coerce").dropna()
                if not numeric.empty:
                    selected_min, selected_max = value
                    full_min = float(numeric.min())
                    full_max = float(numeric.max())
                    try:
                        return (
                            abs(float(selected_min) - full_min) > 0.01
                            or abs(float(selected_max) - full_max) > 0.01
                        )
                    except (TypeError, ValueError):
                        return True
            return True

        return True

    pdf_filter_parts = []
    for label, col, kwargs in pdf_filter_columns:
        value = catalog_filters.get(col)
        if is_active_catalog_filter(col, value):
            pdf_filter_parts.append(
                f"{label}: {format_filter_value(value, **kwargs)}"
            )

    subtitle_lines = [
        f"Zeitraum: {zeitraum_text} · {verlaengerungs_text}"
    ]
    if pdf_filter_parts:
        subtitle_lines.append(" | ".join(pdf_filter_parts))

    pdf_bytes = build_top_media_pdf(
        top_media,
        title=f"Top {len(top_media)} Medien",
        subtitle="\n".join(subtitle_lines),
    )


    st.download_button(
        label="📄 Top-Liste als PDF",
        data=pdf_bytes,
        file_name="top_medien.pdf",
        mime="application/pdf",
    )
# =========================
# 🎨 FIXED COVER STYLE
# =========================
st.markdown(f"""
<style>
.card-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    color: {TEXT};
    font-weight: 600;
    margin-bottom: 0.8rem;
}}
.poster {{
    width: 100%;
    height: 180px;
    object-fit: cover;
    border-radius: 10px;
}}
.poster:hover {{
    transform: scale(1.03);
    transition: 0.2s;
}}
.card-title {{
    font-size: 18px;
    font-weight: 700;
    margin-top: 8px;
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    text-align: center;
    color: {TEXT};
}}

.card-author {{
    font-size: 14px;
    opacity: 0.75;
    margin-top: 2px;
    text-align: center;
}}
.card-count {{
    margin-top: 8px;
    font-size: 15px;
    font-weight: 600;
    color: {PRIMARY};
    text-align: right;
    white-space: nowrap;
}}
.card-series {{
    margin-top: 4px;
    font-size: 0.8rem;
    color: {MUTED};
    font-style: italic;
    text-align:center;
}}
.poster-fallback {{
    border: 1px solid {BORDER};
    background: {COLOR_PLACEHOLDER_BG};
    color: {COLOR_PLACEHOLDER_TEXT};
}}

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
                    cover_url = escape(str(row["URL_Cover"]), quote=True)
                    st.markdown(
                        f"""
                        <img src="{cover_url}" class="poster" alt="">
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(f"""
                    <div class="poster poster-fallback" style="
                        display:flex;
                        align-items:center;
                        justify-content:center;
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
                <div class="card-title">{escape(str(row['MedienTitel']))}</div>
                <div class="card-author">{escape(author if author else "-")}</div>
                <div class="card-series">{escape(str(serie))}</div>                    
                """, unsafe_allow_html=True)
