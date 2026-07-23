import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
from filters import get_sidebar_filters
import altair as alt
import numpy as np

st.set_page_config(page_title="Ausleihen Analyse", page_icon="📊", layout="wide")

# CSS Styles
st.markdown("""
<style>
.main { padding-top: 1rem; }
.block-container { padding-top: 2rem; }
h1 { color: #264653; font-size: 2.2rem; }
h2, h3 { color: #264653; }
[data-testid="stMetric"] { border:1px solid #E6E6E6; border-radius:12px; padding:15px; background:white; box-shadow:0 2px 6px rgba(0,0,0,0.05); }
[data-testid="stSidebar"] { background-color: #fafafa; }
[data-testid="stSidebar"] .stMultiSelect, [data-testid="stSidebar"] .stDateInput { margin-bottom: .6rem; }
[data-testid="stSidebar"] h3 { margin-top: 0.8rem; }
[data-testid="stSidebar"] .stToggle { padding-top: .4rem; padding-bottom: .4rem; }
.filter-chip{ display:inline-block; background:#eef3ff; color:#23405a; border:1px solid #c9d7ff; border-radius:18px; padding:5px 12px; margin:3px; font-size:0.88rem; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Detaillierte Ausleihen-Analyse")

# Debugging
if st.sidebar.checkbox("Debug State anzeigen", value=False):
    st.write("Session State Keys:", [k for k in st.session_state.keys() if 'bib_dashboard' in k])

# ==============================================================================
# 1. DATEN LADEN
# ==============================================================================
if 'data' not in st.session_state or st.session_state['data'] is None:
    st.error("Keine Daten geladen. Bitte starten Sie das Dashboard über die [Startseite](../app.py).")
    st.stop()

data = st.session_state['data']
df_users = data.get("users")
df_loans = data.get("loans")
df_books = data.get("catalog")

if df_users is None:
    st.warning("Keine Nutzerdaten verfügbar.")
    st.stop()
if df_loans is None or df_loans.empty:
    st.warning("Keine Ausleihdaten verfügbar.")
    st.stop()

# ==============================================================================
# 2. FILTER INITIALISIEREN
# ==============================================================================
extra_filters_config = [
    {"label": "🏢 Zweigstelle", "col": "Zweigstelle"},
    {"label": "📚 Medienart", "col": "Medienart"},
    {"label": "📍 Standort", "col": "Standort(1)"}
]

df_users_filtered, df_loans_filtered, filter_info = get_sidebar_filters(
    df_users=df_users,
    df_extra=df_loans,
    prefix="bib_dashboard",
    enable_date_filter=True,
    date_col_name="Ausleihdatum",
    extra_filters_config=extra_filters_config,
    enable_first_loan_toggle=True,
    first_loan_col_name="Erstausleihe"
)

# ==============================================================================
# 3. INFO & AKTIVE FILTER
# ==============================================================================
chips = []
if filter_info.get("date_range"):
    dr = filter_info["date_range"]
    if isinstance(dr, tuple) and len(dr) == 2:
        chips.append(f"📅 {dr[0].strftime('%d.%m.%Y')} – {dr[1].strftime('%d.%m.%Y')}")
        zeitraum_text = f"{dr[0].strftime('%d.%m.%Y')} – {dr[1].strftime('%d.%m.%Y')}"
    else:
        zeitraum_text = "Gesamter Zeitraum"

extra_f = filter_info.get("extra_filters", {})
for col, vals in extra_f.items():
    if vals and len(vals) < df_loans[col].dropna().nunique():
        label = "Medienart" if col == "Medienart" else col
        chips.append(f"{'🏢' if col == 'Zweigstelle' else '📚'} {', '.join(vals)}")

if filter_info.get("groups") and len(filter_info["groups"]) < df_users["Benutzergruppe"].dropna().nunique():
    chips.append(f"👥 {', '.join(filter_info['groups'])}")

if filter_info.get("ss_filter"):
    chips.append(f"🔑 {', '.join(filter_info['ss_filter'])}")

st.markdown("### 🔎 Aktive Filter")
if chips:
    html = "".join([f"<span class='filter-chip'>{chip}</span>" for chip in chips])
    st.markdown(html, unsafe_allow_html=True)
else:
    st.caption("Alle Daten (keine Einschränkung)")

st.divider()
c_meta1, c_meta2 = st.columns(2)
c_meta1.metric("Gefilterte Nutzende", f"{len(df_users_filtered):,}")
c_meta2.metric("Gefilterte Ausleihen", f"{len(df_loans_filtered):,}")

st.divider()

# ==============================================================================
# 4. DATENANREICHERUNG (MERGEN)
# ==============================================================================
merge_key_users = 'Nummer'
merge_key_loans = 'Ausleihperson'

# Prüfung der Schlüsselspalten
if merge_key_users not in df_users_filtered.columns or merge_key_loans not in df_loans_filtered.columns:
    st.error("Fehler: ID-Spalten für den Merge nicht gefunden. Prüfe 'Nummer' und 'Ausleihperson'.")
    st.stop()

# Merge durchführen
df_merged = df_loans_filtered.merge(
    df_users_filtered, 
    left_on=merge_key_loans, 
    right_on=merge_key_users, 
    how='left',
    suffixes=('_ausleihe', '_user')
)


# Benutzergruppe auflösen
group_col_users = None
for col in ['Benutzergruppe', 'Benutzergruppe_Gruppiert', 'Gruppe']:
    if col in df_users_filtered.columns:
        group_col_users = col
        break

if group_col_users:
    candidate = f"{group_col_users}_user"
    if candidate in df_merged.columns:
        df_merged['Benutzergruppe'] = df_merged[candidate]
    else:
        # Fallback
        for col in df_merged.columns:
            if 'Benutzergruppe' in col:
                df_merged['Benutzergruppe'] = df_merged[col]
                break

# Alter berechnen
birth_col = 'Geburtsdatum_user' if 'Geburtsdatum_user' in df_merged.columns else 'Geburtsdatum'
if birth_col in df_merged.columns:
    df_merged['Geburtsdatum_DT'] = pd.to_datetime(df_merged[birth_col], errors='coerce')
    if df_merged['Geburtsdatum_DT'].notna().any():
        today = pd.Timestamp.today()
        df_merged['Alter'] = today.year - df_merged['Geburtsdatum_DT'].dt.year
        m_pass = df_merged['Geburtsdatum_DT'].dt.month < today.month
        d_pass = (df_merged['Geburtsdatum_DT'].dt.month == today.month) & (df_merged['Geburtsdatum_DT'].dt.day <= today.day)
        df_merged.loc[~(m_pass | d_pass), 'Alter'] -= 1
        df_merged.loc[df_merged['Alter'] < 0, 'Alter'] = 0
    else:
        df_merged['Alter'] = None
else:
    df_merged['Alter'] = None

if df_merged.empty:
    st.error("Keine Daten nach dem Merge vorhanden.")
    st.stop()

# ==============================================================================
# 5. TABS STRUKTUR
# ==============================================================================
tab_overview, tab_compare = st.tabs(["📈 Gesamtüberblick", "⚖️ Vergleichsanalyse"])

# ==============================================================================
# TAB 1: GESAMTÜBERBLICK
# ==============================================================================
with tab_overview:
    st.markdown("### 🌍 Entwicklung aller Ausleihen")
    
    # --- CHART 1: ZEITVERLAUF ---
    if not df_loans_filtered.empty:
        df_chart = df_loans_filtered.copy()
        df_chart['Datum'] = pd.to_datetime(df_chart['Ausleihdatum'], errors='coerce')
        df_chart = df_chart.dropna(subset=['Datum'])
        
        if not df_chart.empty:
            df_chart['Jahr'] = df_chart['Datum'].dt.year
            df_chart['Monat_Nummer'] = df_chart['Datum'].dt.month
            
            grouped = df_chart.groupby(['Jahr', 'Monat_Nummer']).size().reset_index(name='Anzahl')
            pivot_data = grouped.pivot(index='Monat_Nummer', columns='Jahr', values='Anzahl').replace(0, pd.NA)
            
            month_names = {1:'Jan', 2:'Feb', 3:'Mär', 4:'Apr', 5:'Mai', 6:'Jun', 7:'Jul', 8:'Aug', 9:'Sep', 10:'Okt', 11:'Nov', 12:'Dez'}
            pivot_data.index = pivot_data.index.map(month_names)
            ordered_months = ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez']
            pivot_data.index = pd.CategoricalIndex(pivot_data.index, categories=ordered_months, ordered=True)
            pivot_data = pivot_data.sort_index()
            pivot_data.index.name = "Monat"
            
            chart_data = pivot_data.reset_index().melt(id_vars="Monat", var_name="Jahr", value_name="Anzahl")
            
            chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X("Monat:N", title="Monat", sort=ordered_months),
                y=alt.Y("Anzahl:Q", title="Ausleihen"),
                xOffset=alt.XOffset("Jahr:N"),
                color=alt.Color("Jahr:N", title="Jahr")
            )
            st.altair_chart(chart, width='stretch')
            
            jahre_list = sorted([int(c) for c in pivot_data.columns])
            if len(jahre_list) > 1:
                st.info(f"Vergleich der Jahre: {', '.join(map(str, jahre_list))}.")
            else:
                st.caption(f"Zeitraum umfasst nur das Jahr {jahre_list[0]}.")
        else:
            st.warning("Keine gültigen Datumsdaten.")
    else:
        st.info("Keine Daten im gewählten Zeitraum.")

    st.divider()
 
    # --- CHART 2 & 3: ÜBERSICHT ---
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📚 Medienart (Gesamt)")
        if "Medienart_x" in df_loans_filtered.columns:
            data = df_loans_filtered["Medienart_x"].fillna("Unbekannt").value_counts().reset_index()
            data.columns = ["Medienart", "Anzahl"]
            st.bar_chart(data.set_index("Medienart"), use_container_width=True)

        else:
            st.error("Keine Daten")
    with c2:
        st.subheader("📅 Wochentag (Gesamt)")
        if "Ausleihdatum" in df_loans_filtered.columns:
            df_temp = df_loans_filtered.dropna(subset=["Ausleihdatum"]).copy()
            if not df_temp.empty:
                if not pd.api.types.is_datetime64_any_dtype(df_temp["Ausleihdatum"]):
                    df_temp["Ausleihdatum"] = pd.to_datetime(df_temp["Ausleihdatum"], errors='coerce')
                df_temp["WD"] = df_temp["Ausleihdatum"].dt.day_name().map({"Monday":"Mo", "Tuesday":"Di", "Wednesday":"Mi", "Thursday":"Do", "Friday":"Fr", "Saturday":"Sa", "Sunday":"So"})
                data = df_temp.groupby("WD").size().reindex(["Mo","Di","Mi","Do","Fr","Sa","So"], fill_value=0).reset_index(name="Anzahl")
                wochentage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

                chart = (
                    alt.Chart(data)
                    .mark_bar()
                    .encode(
                        x=alt.X(
                            "WD:N",
                            sort=wochentage,
                            title="Wochentag"
                        ),
                        y=alt.Y(
                            "Anzahl:Q",
                            title="Ausleihen"
                        ),
                        tooltip=["WD", "Anzahl"]
                    )
                )

                st.altair_chart(chart, use_container_width=True)

# ==============================================================================
# TAB 2: VERGLEICHSANALYSE
# ==============================================================================
with tab_compare:
    st.markdown("### 🔍 Zielgruppen-Vergleich")
    st.caption("Vergleiche zwei beliebige Segmente miteinander.")
    
    if 'Benutzergruppe' not in df_merged.columns:
        st.warning("Keine Benutzergruppen-Daten verfügbar.")
    
    dim_option = st.radio("Vergleichen nach:", ["Benutzergruppe", "Altersgruppe (Flexibel)"], horizontal=True)
    
    df_compare = None
    label_a = ""
    label_b = ""

    # LOGIK BENUTZERGRUPPE
    if dim_option == "Benutzergruppe":
        if 'Benutzergruppe' in df_merged.columns:
            groups = sorted(df_merged['Benutzergruppe'].dropna().unique())
            if len(groups) >= 2:
                c1, c2 = st.columns(2)
                with c1:
                    g1 = st.selectbox("Gruppe A", groups, key="sel_g1")
                with c2:
                    g2 = st.selectbox("Gruppe B", groups, index=1 if len(groups)>1 else 0, key="sel_g2")
                
                if g1 != g2:
                    label_a, label_b = g1, g2
                    df_compare = df_merged[df_merged['Benutzergruppe'].isin([g1, g2])].copy()
                    df_compare['Vergleichsgruppe'] = df_compare['Benutzergruppe']
                else:
                    st.info("Bitte zwei verschiedene Gruppen wählen.")
            else:
                st.warning("Nicht genug Gruppen für einen Vergleich.")

    # LOGIK ALTER
    elif dim_option == "Altersgruppe (Flexibel)":
        if df_merged['Alter'].notna().any():
            min_a, max_a = int(df_merged['Alter'].min()), int(df_merged['Alter'].max())
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("🔵 **Gruppe A**")
                range_a = st.slider("Alter A", min_a, max_a, (min_a, 25), key="slide_a")
                label_a = f"{range_a[0]}-{range_a[1]} J."
            with c2:
                st.markdown("🔴 **Gruppe B**")
                start_b = min(range_a[1] + 1, max_a)
                range_b = st.slider("Alter B", min_a, max_a, (start_b, max_a), key="slide_b")
                label_b = f"{range_b[0]}-{range_b[1]} J."
            
            mask_a = (df_merged['Alter'] >= range_a[0]) & (df_merged['Alter'] <= range_a[1])
            mask_b = (df_merged['Alter'] >= range_b[0]) & (df_merged['Alter'] <= range_b[1])
            
            df_temp = df_merged.copy()
            df_temp['Vergleichsgruppe'] = None
            df_temp.loc[mask_a, 'Vergleichsgruppe'] = label_a
            df_temp.loc[mask_b, 'Vergleichsgruppe'] = label_b
            df_compare = df_temp[df_temp['Vergleichsgruppe'].notna()].copy()
        else:
            st.warning("Keine Altersdaten verfügbar.")

    # --- CHARTS FÜR VERGLEICH ---
    if df_compare is not None and not df_compare.empty:
        st.divider()
        st.success(
            f"Vergleich: **{label_a}** vs. **{label_b}**\n\n"
            f"📅 Zeitraum: **{zeitraum_text}**"
        )
        
        # Medienart
        st.markdown("#### 📚 Medienart-Präferenzen")
        if "Medienart" in df_compare.columns:
            data = df_compare.groupby(['Medienart', 'Vergleichsgruppe']).size().reset_index(name='Anzahl')
            chart = alt.Chart(data).mark_bar().encode(
                x=alt.X('Medienart:N', sort='-y'),
                y=alt.Y('Anzahl:Q'),
                color=alt.Color('Vergleichsgruppe:N', scale=alt.Scale(domain=[label_a, label_b], range=['#1f77b4', '#d62728'])),
                xOffset='Vergleichsgruppe:N',
                tooltip=['Medienart', 'Vergleichsgruppe', 'Anzahl']
            ).properties(
                title=f"Medienart-Präferenzen ({zeitraum_text})",
                height=350
            ).interactive()
            st.altair_chart(chart, width='stretch')
        
        # Wochentag
        st.markdown("#### 📅 Ausleihtage")
        df_wd = df_compare.dropna(subset=['Ausleihdatum']).copy()
        if not df_wd.empty:
            df_wd['Datum'] = pd.to_datetime(df_wd['Ausleihdatum'], errors='coerce')
            df_wd['WD'] = df_wd['Datum'].dt.day_name().map({"Monday":"Mo", "Tuesday":"Di", "Wednesday":"Mi", "Thursday":"Do", "Friday":"Fr", "Saturday":"Sa", "Sunday":"So"})
            data = df_wd.groupby(['WD', 'Vergleichsgruppe']).size().reset_index(name='Anzahl')
            chart = alt.Chart(data).mark_bar().encode(
                x=alt.X('WD:N', sort=["Mo","Di","Mi","Do","Fr","Sa","So"]),
                y=alt.Y('Anzahl:Q'),
                color=alt.Color('Vergleichsgruppe:N', scale=alt.Scale(domain=[label_a, label_b], range=['#1f77b4', '#d62728'])),
                xOffset='Vergleichsgruppe:N',
                tooltip=['WD', 'Vergleichsgruppe', 'Anzahl']
            ).properties(
                title=f"Ausleihtage ({zeitraum_text})",
                height=300
            )
            st.altair_chart(chart, width='stretch')

        # Tabelle
        st.markdown(f"#### 📊 Aktivitätsniveau (Ø Ausleihen pro Person im Zeitraum {zeitraum_text})")
        id_col = 'Ausleihperson'
        if id_col in df_compare.columns:
            stats = df_compare.groupby([id_col, 'Vergleichsgruppe']).size().reset_index(name='Count')
            avg = stats.groupby('Vergleichsgruppe')['Count'].mean().reset_index()
            avg.columns = ['Gruppe', 'Ø Ausleihen']
            st.dataframe(avg.style.format({'Ø Ausleihen': '{:.1f}'}), hide_index=True, width='stretch')
    else:
        st.info("👈 Bitte konfigurieren Sie oben den Vergleich, um Ergebnisse zu sehen.")

# st.subheader("📍 Ausleihen nach Medienart")
if "Medienart_x" in df_merged.columns:

    with st.expander("📍 Ausleihen und Bestandsnutzung nach Medienart"):

        col1, col2, col3 = st.columns(3)

        # -------------------------------------------------
        # LINKER PLOT: AUSLEIHEN
        # -------------------------------------------------
        with col1:
            st.markdown("**📚 Ausleihen nach Medienart**")

            medienart = (
                df_merged["Medienart_x"]
                .fillna("Unbekannt")
                .astype(str)
                .str.strip()
                .value_counts()
                .reset_index()
            )

            medienart.columns = ["Medienart", "Ausleihen"]

            medienart["Anteil"] = (
                medienart["Ausleihen"] /
                medienart["Ausleihen"].sum()
                * 100
            )

            medienart["Anteil_Label"] = (
                medienart["Anteil"]
                .map(lambda x: f"{x:.1f}%")
            )
            medienart = (
                medienart
                .sort_values("Ausleihen", ascending=False)
                .head(10)
            )
            bars = (
                alt.Chart(medienart)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "Ausleihen:Q",
                        title="Ausleihen",
                        axis=alt.Axis(format=".0f")
                    ),
                    y=alt.Y(
                        "Medienart:N",
                        sort="-x",
                        title=""
                    ),
                    tooltip=[
                        "Medienart",
                        "Ausleihen",
                        alt.Tooltip(
                            "Anteil:Q",
                            title="Anteil %",
                            format=".1f"
                        )
                    ]
                )
            )

            text = (
                alt.Chart(medienart)
                .mark_text(
                    align="left",
                    dx=5
                )
                .encode(
                    x="Ausleihen:Q",
                    y=alt.Y(
                        "Medienart:N",
                        sort="-x"
                    ),
                    text="Anteil_Label:N"
                )
            )

            st.altair_chart(
                (bars + text).properties(height=300),
                use_container_width=True
            )


        # -------------------------------------------------
        # RECHTER PLOT: UMSATZ
        # -------------------------------------------------
        with col2:
            

            bestand = (
                df_books["Medienart"]
                .fillna("Unbekannt")
                .astype(str)
                .str.strip()
                .value_counts()
                .reset_index()
            )

            bestand.columns = [
                "Medienart",
                "Bestand"
            ]

            ausleihen = (
                df_merged["Medienart_y"]
                .fillna("Unbekannt")
                .astype(str)
                .str.strip()
                .value_counts()
                .reset_index()
            )

            ausleihen.columns = [
                "Medienart",
                "Ausleihen"
            ]

            medienart_effizienz = ausleihen.merge(
                bestand,
                on="Medienart",
                how="outer"
            ).fillna(0)

            medienart_effizienz["Umlauf"] = (
                medienart_effizienz["Ausleihen"] /
                medienart_effizienz["Bestand"]
            )
            medienart_effizienz = (
                medienart_effizienz
                .sort_values("Umlauf", ascending=False)
                .head(10)
            )
            medienart_effizienz["Bestandsanteil"] = (
                medienart_effizienz["Bestand"]
                / medienart_effizienz["Bestand"].sum()
            )

            medienart_effizienz["Ausleihanteil"] = (
                medienart_effizienz["Ausleihen"]
                / medienart_effizienz["Ausleihen"].sum()
            )
            medienart_effizienz["Effizienz"] = (
                medienart_effizienz["Ausleihanteil"]
                / medienart_effizienz["Bestandsanteil"]
            )
            gesamt_ausleihen = medienart_effizienz["Ausleihen"].sum()
            gesamt_bestand = medienart_effizienz["Bestand"].sum()

            gesamt_umlauf = (
                gesamt_ausleihen / gesamt_bestand
                if gesamt_bestand > 0 else 0
            )
            st.markdown("**📈 Umsatz (Ausleihen/ Bestand)** "
                        f"Gesamt: **{gesamt_umlauf:.2f}** Ausleihen je Medium")
                        
            chart = (
                alt.Chart(medienart_effizienz)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "Umlauf:Q",
                        title="Ausleihen pro Medium",
                        axis=alt.Axis(format=".1f")
                    ),
                    y=alt.Y(
                        "Medienart:N",
                        sort="-x",
                        title=""
                    ),
                    tooltip=[
                        "Medienart",
                        "Bestand",
                        "Ausleihen",
                        alt.Tooltip(
                            "Umlauf:Q",
                            title="Umsatz",
                            format=".2f"
                        )
                    ]
                )
                .properties(height=300)
            )

            st.altair_chart(
                chart,
                use_container_width=True
            )
        with col3:
            st.markdown("**📈 Effizienz (Ausleihanteil / Bestandesanteil)** ")
            rule = (
                alt.Chart(pd.DataFrame({"Effizienz": [1]}))
                .mark_rule(strokeDash=[4, 4], color="red")
                .encode(
                    x="Effizienz:Q"
                )
            )
                        
            chart = (
                alt.Chart(medienart_effizienz)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "Effizienz:Q",
                        title="Ausleihanteil / Bestandsanteil",
                        axis=alt.Axis(format=".1f")
                    ),
                    y=alt.Y(
                        "Medienart:N",
                        sort="-x",
                        title=""
                    ),
                    tooltip=[
                        "Medienart",
                        alt.Tooltip("Bestand:Q", format=",.0f"),
                        alt.Tooltip("Ausleihen:Q", format=",.0f"),
                        alt.Tooltip("Bestandsanteil:Q", title="Bestandsanteil", format=".1%"),
                        alt.Tooltip("Ausleihanteil:Q", title="Ausleihanteil", format=".1%"),
                        alt.Tooltip("Umlauf:Q", title="Umsatz", format=".2f"),
                        alt.Tooltip("Effizienz:Q", format=".2f"),
                    ]
                )
                .properties(height=300)
            )

            st.altair_chart(
                chart+rule,
                use_container_width=True
            )
# st.subheader("📍 Ausleihen nach Standort")
if "Standort(1)" in df_merged.columns:

    with st.expander("📍 Ausleihen und Bestandsnutzung nach Medienstandort"):

        col1, col2 = st.columns(2)

        # -------------------------------------------------
        # LINKER PLOT: AUSLEIHEN
        # -------------------------------------------------
        with col1:
            st.markdown("**📚 Ausleihen nach Standort**")

            standort = (
                df_merged["Standort(1)"]
                .fillna("Unbekannt")
                .astype(str)
                .str.strip()
                .value_counts()
                .reset_index()
            )

            standort.columns = ["Standort", "Ausleihen"]

            standort["Anteil"] = (
                standort["Ausleihen"] /
                standort["Ausleihen"].sum()
                * 100
            )

            standort["Anteil_Label"] = (
                standort["Anteil"]
                .map(lambda x: f"{x:.1f}%")
            )
            standort = (
                standort
                .sort_values("Ausleihen", ascending=False)
                .head(10)
            )

            bars = (
                alt.Chart(standort)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "Ausleihen:Q",
                        title="Ausleihen",
                        axis=alt.Axis(format=".0f")
                    ),
                    y=alt.Y(
                        "Standort:N",
                        sort="-x",
                        title=""
                    ),
                    tooltip=[
                        "Standort",
                        "Ausleihen",
                        alt.Tooltip(
                            "Anteil:Q",
                            title="Anteil %",
                            format=".1f"
                        )
                    ]
                )
            )

            text = (
                alt.Chart(standort)
                .mark_text(
                    align="left",
                    dx=5
                )
                .encode(
                    x="Ausleihen:Q",
                    y=alt.Y(
                        "Standort:N",
                        sort="-x"
                    ),
                    text="Anteil_Label:N"
                )
            )

            st.altair_chart(
                (bars + text).properties(height=300),
                use_container_width=True
            )


        # -------------------------------------------------
        # RECHTER PLOT: UMSATZ
        # -------------------------------------------------
        with col2:

            bestand = (
                df_books["Standort(1)"]
                .fillna("Unbekannt")
                .astype(str)
                .str.strip()
                .value_counts()
                .reset_index()
            )

            bestand.columns = [
                "Standort",
                "Bestand"
            ]

            ausleihen = (
                df_merged["Standort(1)"]
                .fillna("Unbekannt")
                .astype(str)
                .str.strip()
                .value_counts()
                .reset_index()
            )

            ausleihen.columns = [
                "Standort",
                "Ausleihen"
            ]

            standort_effizienz = ausleihen.merge(
                bestand,
                on="Standort",
                how="outer"
            ).fillna(0)

            standort_effizienz["Umlauf"] = (
                standort_effizienz["Ausleihen"] /
                standort_effizienz["Bestand"]
            )
            standort_effizienz = (
                standort_effizienz
                .sort_values('Umlauf', ascending=False)
                .head(10)
            )
            gesamt_ausleihen = standort_effizienz["Ausleihen"].sum()
            gesamt_bestand = standort_effizienz["Bestand"].sum()

            gesamt_umlauf = (
                gesamt_ausleihen / gesamt_bestand
                if gesamt_bestand > 0 else 0
            )
            st.markdown("**📈 Bestandsnutzung (Umsatz)** "
                        f"Gesamt **{gesamt_umlauf:.2f}** Ausleihen je Medium)")
            chart = (
                alt.Chart(standort_effizienz)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "Umlauf:Q",
                        title="Ausleihen pro Medium",
                        axis=alt.Axis(format=".1f")
                    ),
                    y=alt.Y(
                        "Standort:N",
                        sort="-x",
                        title=""
                    ),
                    tooltip=[
                        "Standort",
                        "Bestand",
                        "Ausleihen",
                        alt.Tooltip(
                            "Umlauf:Q",
                            title="Umsatz",
                            format=".2f"
                        )
                    ]
                )
                .properties(
                    height=300)
            )

            st.altair_chart(
                chart,
                use_container_width=True
            )