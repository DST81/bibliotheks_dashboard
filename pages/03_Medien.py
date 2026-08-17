import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime
from src.filters import get_sidebar_filters, build_filtered_data
from src.media_helpers import kategorie_bereinigen, sortierter_balken
from src.pdf_report import build_report_pdf
from src.report_helpers import (
    apply_loan_context_filters,
    apply_non_date_catalog_filters,
    build_media_filter_summary,
    build_yearly_media_kpis,
    delta_color,
    format_delta,
    format_pdf_delta,
)
from components.ui import kpi_box, show_new_acquisition_detail

st.set_page_config(page_title="Medien Analyse", page_icon="📚", layout="wide")

st.title("Medien Analyse")

# --------------------------------------------------------
# Prüfen, ob Daten geladen wurden
# --------------------------------------------------------
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
    prefix="ausleihe",
    enable_date_filter=True,
    enable_first_loan_toggle=True,
    extra_filters_config=[
        {"col": "Zweigstelle", "label": "Zweigstelle"},
    ],
    catalog_filters_config=[
        {"col": "Lieferant", "label": "Lieferant", "type": "multiselect"},
        {"col": "Preis", "label": "Preis", "type": "range", "currency": True, "step": 5.0},
        {
            "col": "Datum der Aufnahme",
            "label": "Neuanschaffung",
            "type": "date_preset",
            "default": "Aktuelles Jahr",
        },
        {"col": "Sprache(1)", "label": "Sprache", "type": "multiselect"},
        {"col": "Medienart", "label": "Medienart", "type": "multiselect"},
        {"col": "Kategorie Alter", "label": "Lesealter", "type": "multiselect"},
        {"col": "Standort(1)", "label": "Standort", "type": "multiselect"},
    ],
    expander_defaults={
        "target": False,
        "loans": False,
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
df_books_used = filtered_data['books_used']


# ============================================================
# 💰 NEUANSCHAFFUNGEN – DATEN VORBEREITEN (für alle Tabs)
# ============================================================
st.header("💰 Neuanschaffungen und Beschaffungskosten")
st.caption(
    "Auswertung der gefilterten Katalogmedien nach Lieferant, "
    "Preis und Ausleihnutzung"
)

required_new_cols = {"NR Zugang", "Titel", "Lieferant", "Preis", "Datum der Aufnahme"}
missing_new_cols = required_new_cols - set(df_katalog.columns)

if missing_new_cols:
    st.warning(
        "Für die Neuanschaffungsanalyse fehlen folgende Spalten: "
        + ", ".join(sorted(missing_new_cols))
    )
    st.stop()

df_new = df_katalog.copy()

# Preis
df_new["Preis"] = pd.to_numeric(df_new["Preis"], errors="coerce")

# Datum
df_new["Datum der Aufnahme"] = pd.to_datetime(df_new["Datum der Aufnahme"], errors="coerce")

# Lieferant
df_new = kategorie_bereinigen(df_new, "Lieferant")

# Ausleihen pro Medium
if "NR Zugang" in df_ausleihe.columns:
    ausleih_counts_new = (
        df_ausleihe
        .groupby("NR Zugang")
        .size()
        .reset_index(name="_Ausleihen_neu")
    )

    if "Ausleihen" in df_new.columns:
        df_new = df_new.drop(columns=["Ausleihen"])

    df_new = df_new.merge(ausleih_counts_new, on="NR Zugang", how="left")
    df_new = df_new.rename(columns={"_Ausleihen_neu": "Ausleihen"})
else:
    df_new["Ausleihen"] = 0

df_new["Ausleihen"] = (
    pd.to_numeric(df_new["Ausleihen"], errors="coerce").fillna(0).astype(int)
)

if df_new.empty:
    st.info(
        "ℹ️ Für die aktuelle Filterauswahl wurden keine "
        "Neuanschaffungen gefunden. Bitte passen Sie die Filter an."
    )
    st.stop()

# ============================================================
# KENNZAHLEN (aktuelles Jahr mit Vorjahresvergleich)
# ============================================================
aktuelles_jahr = datetime.now().year
vorjahr = aktuelles_jahr - 1

df_katalog_base = data.get("catalog")
if df_katalog_base is None:
    df_katalog_base = pd.DataFrame()

df_loans_base = data.get("loans")
if df_loans_base is None:
    df_loans_base = pd.DataFrame()

kpis_aktuell = build_yearly_media_kpis(
    df_katalog_base,
    df_loans_base,
    df_users,
    filter_state,
    aktuelles_jahr,
)
kpis_vorjahr = build_yearly_media_kpis(
    df_katalog_base,
    df_loans_base,
    df_users,
    filter_state,
    vorjahr,
)

anzahl_neu = kpis_aktuell["media_count"]
gesamtkosten = kpis_aktuell["total_cost"]
durchschnittspreis = kpis_aktuell["avg_price"]
gesamtausleihen = kpis_aktuell["loan_count"]
durchschnittliche_ausleihen = kpis_aktuell["avg_loans"]

st.subheader(f"Kennzahlen {aktuelles_jahr}")

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

with kpi1:
    kpi_box(
        "📚 Neuanschaffungen",
        anzahl_neu,
        previous=kpis_vorjahr["media_count"],
        previous_label=f"{vorjahr}",
        subtext=format_delta(anzahl_neu, kpis_vorjahr["media_count"]),
        color=delta_color(anzahl_neu, kpis_vorjahr["media_count"]),
    )
with kpi2:
    kpi_box(
        "💰 Gesamtkosten",
        f"CHF {gesamtkosten:,.0f}".replace(",", "'"),
        previous=f"{vorjahr}: CHF {kpis_vorjahr['total_cost']:,.0f}".replace(",", "'"),
        subtext=format_delta(gesamtkosten, kpis_vorjahr["total_cost"]),
        color=delta_color(gesamtkosten, kpis_vorjahr["total_cost"]),
    )
with kpi3:
    kpi_box(
        "Ø Preis",
        f"CHF {durchschnittspreis:,.2f}".replace(",", "'"),
        previous=f"{vorjahr}: CHF {kpis_vorjahr['avg_price']:,.2f}".replace(",", "'"),
        subtext=format_delta(durchschnittspreis, kpis_vorjahr["avg_price"]),
        color=delta_color(durchschnittspreis, kpis_vorjahr["avg_price"]),
    )
with kpi4:
    kpi_box(
        "📊 Ausleihen",
        gesamtausleihen,
        previous=kpis_vorjahr["loan_count"],
        previous_label=f"{vorjahr}",
        subtext=format_delta(gesamtausleihen, kpis_vorjahr["loan_count"]),
        color=delta_color(gesamtausleihen, kpis_vorjahr["loan_count"]),
    )
with kpi5:
    kpi_box(
        "Ø Ausl./Medium",
        f"{durchschnittliche_ausleihen:.1f}",
        previous=f"{vorjahr}: {kpis_vorjahr['avg_loans']:.1f}",
        subtext=format_delta(durchschnittliche_ausleihen, kpis_vorjahr["avg_loans"]),
        color=delta_color(durchschnittliche_ausleihen, kpis_vorjahr["avg_loans"]),
    )

# Lieferanten-Basisliste (wird vom Scatterplot-Filter gebraucht;
# die volle Auswertung nach Lieferant liefert Tab "Vergleiche").
alle_lieferanten = sorted(df_new["Lieferant"].dropna().astype(str).unique().tolist())
kosten_je_lieferant = (
    df_new.groupby("Lieferant")["Preis"].sum().sort_values(ascending=False)
)
alle_lieferanten = [l for l in kosten_je_lieferant.index if l in alle_lieferanten]

# ============================================================
# TABS
# ============================================================
tab_vergleich, tab_jahresvergleich, tab_scatter = st.tabs(
    ["📊 Vergleiche", "📈 Jahresvergleich", "🔍 Preis & Nutzung"]
)

# ============================================================
# TAB 3: PREIS & NUTZUNG (Scatterplot je Medium)
# ============================================================
with tab_scatter:
    st.caption(
        "Jeder Punkt entspricht einem Medium. "
        "So lässt sich erkennen, ob teurere Anschaffungen "
        "häufiger genutzt werden."
    )

    scatter_df = df_new.copy()

    benoetigte_spalten = [
        "NR Zugang", "Titel", "Verfasser I(1)", "Lieferant", "Preis",
        "Ausleihen", "Datum der Aufnahme", "Reihe(1)", "Band", "URL_Cover"
    ]
    benoetigte_spalten = [c for c in benoetigte_spalten if c in scatter_df.columns]
    scatter_df = scatter_df[benoetigte_spalten].copy()

    # Standardmässig nur die Top-Lieferanten nach Ausgaben anzeigen,
    # sonst wird der Plot bei vielen Lieferanten schnell unübersichtlich.
    # alle_lieferanten ist bereits nach Kosten absteigend sortiert.
    TOP_N_STANDARD = 8
    standard_lieferanten = alle_lieferanten[:TOP_N_STANDARD]

    # Default: Top-Lieferanten, auch falls scatter_df leer ist
    # (verhindert einen NameError in der Detailtabelle weiter unten)
    sichtbare_lieferanten = standard_lieferanten

    if scatter_df.empty:
        st.info("Keine ausreichenden Daten für die Preis-/Nutzungsanalyse vorhanden.")

    else:
        sichtbare_lieferanten = st.multiselect(
            "Lieferanten anzeigen",
            options=alle_lieferanten,
            default=standard_lieferanten,
            key='neu_lieferanten_scatter',
            help=(
                f"Standardmässig werden die {TOP_N_STANDARD} Lieferanten "
                "mit den höchsten Ausgaben angezeigt. Fügen Sie bei Bedarf "
                "weitere hinzu oder wählen Sie alle ab."
            )
        )

        # Scatterplot tatsächlich auf die Auswahl einschränken
        scatter_df = scatter_df[scatter_df["Lieferant"].isin(sichtbare_lieferanten)].copy()

    if scatter_df.empty and sichtbare_lieferanten is not None and len(sichtbare_lieferanten) == 0:
        st.info("Bitte wählen Sie mindestens einen Lieferanten aus, um Punkte anzuzeigen.")

    if sichtbare_lieferanten and not scatter_df.empty:
        np.random.seed(42)
        scatter_df["Preis_Jitter"] = (
            scatter_df["Preis"] + np.random.uniform(-0.15, 0.15, size=len(scatter_df))
        )
        scatter_df["Ausleihen_Jitter"] = (
            scatter_df["Ausleihen"] + np.random.uniform(-0.12, 0.12, size=len(scatter_df))
        )

        punkt_klick = alt.selection_point(
            fields=["NR Zugang"], name="punkt_klick", on="click", empty=False,
        )

        scatter_df["Reihe_Band"] = scatter_df.apply(
            lambda r: (
                f"{r['Reihe(1)']} (Band {r['Band']})"
                if (
                    "Reihe(1)" in scatter_df.columns
                    and pd.notna(r["Reihe(1)"])
                    and str(r["Reihe(1)"]).strip() != ""
                )
                else None
            ),
            axis=1
        )

        scatter = (
            alt.Chart(scatter_df)
            .mark_circle(opacity=0.7, stroke="white", strokeWidth=0.5)
            .encode(
                x=alt.X("Preis_Jitter:Q", title="Preis (CHF)", scale=alt.Scale(zero=False)),
                y=alt.Y("Ausleihen_Jitter:Q", title="Anzahl Ausleihen", axis=alt.Axis(format=".0f")),
                color=alt.Color("Lieferant:N", title="Lieferant"),
                tooltip=[
                    alt.Tooltip("Titel:N", title="Titel"),
                    alt.Tooltip("Verfasser I(1):N", title="Autor"),
                    alt.Tooltip("Reihe_Band:N", title="Reihe"),
                    alt.Tooltip("Lieferant:N", title="Lieferant"),
                    alt.Tooltip("Preis:Q", title="Preis", format=".2f"),
                    alt.Tooltip("Ausleihen:Q", title="Ausleihen gesamt", format=".0f"),
                    alt.Tooltip("Datum der Aufnahme:T", title="Aufnahme"),
                    alt.Tooltip("NR Zugang:N", title="NR Zugang"),
                ]
            )
            .add_params(punkt_klick)
            .properties(height=400)
            .interactive()
        )

        event = st.altair_chart(
            scatter, width="stretch", on_select="rerun", key="neuanschaffungen_scatter"
        )

        selektierte_nr = None
        if event and "selection" in event:
            punkte = event["selection"].get("punkt_klick", [])
            if punkte:
                selektierte_nr = punkte[0].get("NR Zugang")

        if selektierte_nr is not None:
            treffer = scatter_df[scatter_df["NR Zugang"] == selektierte_nr]
            if not treffer.empty:
                st.session_state.selected_medium = treffer.iloc[0]
                st.session_state.selection_source = "neuanschaffungen_scatter"

    detail_placeholder = st.empty()
    with detail_placeholder.container():
        if st.session_state.get("selected_medium") is not None:
            show_new_acquisition_detail(st.session_state["selected_medium"])
        else:
            st.info("👉 Klicken Sie auf einen Punkt im Diagramm, um die Detailansicht des Mediums zu öffnen.")


# ============================================================
# GEMEINSAME DIMENSIONS-OPTIONEN für Vergleich & Jahresvergleich
# ============================================================
DIMENSION_OPTIONEN = {
    "👶 Lesealter": "Kategorie Alter",
    "📚 Medienart": "Medienart",
    "📍 Standort": "Standort(1)",
    "🏢 Lieferant": "Lieferant",
}


# ============================================================
# TAB 1: VERGLEICHE (ohne Jahresfokus)
# ============================================================
with tab_vergleich:
    st.caption(
        "Vergleichen Sie die aktuell gefilterten Neuanschaffungen "
        "nach Medienart, Lesealter, Standort oder Lieferant."
    )

    dimension_label = st.radio(
        "Vergleichen nach",
        options=list(DIMENSION_OPTIONEN.keys()),
        horizontal=True,
        key="vergleich_dimension"
    )
    dimension_spalte = DIMENSION_OPTIONEN[dimension_label]

    if dimension_spalte not in df_new.columns:
        st.warning(f"Die Spalte '{dimension_spalte}' ist im Katalog nicht vorhanden.")
        st.stop()

    vergleich_df = df_new.copy()
    vergleich_df = kategorie_bereinigen(vergleich_df, dimension_spalte)

    vergleich = (
        vergleich_df
        .groupby(dimension_spalte, dropna=False)
        .agg(
            Medien=("NR Zugang", "nunique"),
            Kosten=("Preis", "sum"),
            Durchschnittspreis=("Preis", "mean"),
            Ausleihen=("Ausleihen", "sum"),
        )
        .reset_index()
        .rename(columns={dimension_spalte: "Vergleich"})
    )

    vergleich["Ausleihen pro Medium"] = np.where(
        vergleich["Medien"] > 0, vergleich["Ausleihen"] / vergleich["Medien"], 0
    )

    # Ausleihen pro CHF 100
    # Beispiel: 10 Ausleihen bei CHF 200 Kosten = 5 Ausleihen pro CHF 100
    vergleich["Ausleihen pro CHF 100"] = np.where(
        vergleich["Kosten"] > 0, vergleich["Ausleihen"] / vergleich["Kosten"] * 100, 0
    )

    vergleich = vergleich.sort_values("Kosten", ascending=False).reset_index(drop=True)

    # --------------------------------------------------------
    # DIAGRAMM
    # --------------------------------------------------------
    st.subheader(f"Vergleich nach {dimension_label.split(' ', 1)[-1]}")

    diagramm_art = st.selectbox(
        "Kennzahl im Diagramm",
        options=["Medien", "Kosten", "Durchschnittspreis", "Ausleihen",
                 "Ausleihen pro Medium", "Ausleihen pro CHF 100"],
        key="vergleich_kennzahl"
    )

    achsen_titel = {
        "Medien": "Anzahl Medien",
        "Kosten": "Kosten (CHF)",
        "Durchschnittspreis": "Ø Preis (CHF)",
        "Ausleihen": "Anzahl Ausleihen",
        "Ausleihen pro Medium": "Ø Ausleihen pro Medium",
        "Ausleihen pro CHF 100": "Ausleihen pro CHF 100",
    }

    st.altair_chart(
        sortierter_balken(
            vergleich, "Vergleich", diagramm_art,
            dimension_label.split(" ", 1)[-1], achsen_titel[diagramm_art]
        ),
        use_container_width=True
    )

    # --------------------------------------------------------
    # VERGLEICHSTABELLE
    # --------------------------------------------------------
    st.subheader("📋 Detailvergleich")

    tabelle = vergleich.copy()
    tabelle["Kosten"] = tabelle["Kosten"].round(2)
    tabelle["Durchschnittspreis"] = tabelle["Durchschnittspreis"].round(2)
    tabelle["Ausleihen pro Medium"] = tabelle["Ausleihen pro Medium"].round(1)
    tabelle["Ausleihen pro CHF 100"] = tabelle["Ausleihen pro CHF 100"].round(1)

    tabelle = tabelle.rename(
        columns={
            "Vergleich": dimension_label.split(" ", 1)[-1],
            "Kosten": "Kosten (CHF)",
            "Durchschnittspreis": "Ø Preis (CHF)",
            "Ausleihen pro Medium": "Ø Ausleihen / Medium",
            "Ausleihen pro CHF 100": "Ausleihen / CHF 100",
        }
    )

    st.dataframe(tabelle, use_container_width=True, hide_index=True)


# ============================================================
# TAB 2: JAHRESVERGLEICH
# ============================================================
with tab_jahresvergleich:
    st.caption(
        "Vergleichen Sie Ausgaben und Nutzung zwischen zwei Jahren "
        "(basierend auf der aktuellen Filterauswahl; der Filter "
        "«Neuanschaffung» wird hier ignoriert, da die Jahre explizit gewählt werden)."
    )

    dimension_label_jv = st.radio(
        "Vergleichen nach",
        options=list(DIMENSION_OPTIONEN.keys()),
        horizontal=True,
        key="jahresvergleich_dimension"
    )
    dimension_spalte_jv = DIMENSION_OPTIONEN[dimension_label_jv]

    jahresvergleich_df = apply_non_date_catalog_filters(
        df_katalog_base,
        filter_state.get("catalog_filters", {}),
    )

    if dimension_spalte_jv not in jahresvergleich_df.columns:
        st.warning(f"Die Spalte '{dimension_spalte_jv}' ist im Katalog nicht vorhanden.")
        st.stop()

    jahresvergleich_df["Preis"] = pd.to_numeric(jahresvergleich_df["Preis"], errors="coerce")
    jahresvergleich_df["Datum der Aufnahme"] = pd.to_datetime(
        jahresvergleich_df["Datum der Aufnahme"],
        errors="coerce",
    )
    jahresvergleich_df["NR Zugang"] = jahresvergleich_df["NR Zugang"].astype(str)
    if "Ausleihen" in jahresvergleich_df.columns:
        jahresvergleich_df = jahresvergleich_df.drop(columns=["Ausleihen"])

    jahresvergleich_df["Anschaffungsjahr"] = jahresvergleich_df["Datum der Aufnahme"].dt.year
    jahresvergleich_df = jahresvergleich_df[jahresvergleich_df["Anschaffungsjahr"].notna()].copy()
    jahresvergleich_df["Anschaffungsjahr"] = jahresvergleich_df["Anschaffungsjahr"].astype(int)
    jahresvergleich_df = kategorie_bereinigen(jahresvergleich_df, dimension_spalte_jv)

    loans_jv = apply_loan_context_filters(
        df_loans_base,
        df_users,
        filter_state,
        year=None,
    )

    if "NR Zugang" in loans_jv.columns and "Ausleihdatum" in loans_jv.columns:
        loans_jv = loans_jv.copy()
        loans_jv["NR Zugang"] = loans_jv["NR Zugang"].astype(str)
        loans_jv["Ausleihjahr"] = pd.to_datetime(
            loans_jv["Ausleihdatum"],
            errors="coerce",
        ).dt.year
        loans_jv = loans_jv[loans_jv["Ausleihjahr"].notna()].copy()
        loans_jv["Ausleihjahr"] = loans_jv["Ausleihjahr"].astype(int)

        ausleih_counts_jv = (
            loans_jv
            .groupby(["NR Zugang", "Ausleihjahr"])
            .size()
            .reset_index(name="Ausleihen")
            .rename(columns={"Ausleihjahr": "Anschaffungsjahr"})
        )

        jahresvergleich_df = jahresvergleich_df.merge(
            ausleih_counts_jv,
            on=["NR Zugang", "Anschaffungsjahr"],
            how="left",
        )
    else:
        jahresvergleich_df["Ausleihen"] = 0

    jahresvergleich_df["Ausleihen"] = (
        pd.to_numeric(jahresvergleich_df["Ausleihen"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    verfuegbare_jahre = sorted(jahresvergleich_df["Anschaffungsjahr"].unique(), reverse=True)

    if len(verfuegbare_jahre) < 2:
        st.info("ℹ️ Für einen Jahresvergleich werden mindestens zwei Jahre mit Daten benötigt.")

    else:
        col_jahr1, col_jahr2 = st.columns(2)

        with col_jahr1:
            jahr_aktuell = st.selectbox(
                "Aktuelles Jahr", options=verfuegbare_jahre, index=0, key="jahresvergleich_aktuell"
            )
        with col_jahr2:
            jahr_vorjahr_optionen = [j for j in verfuegbare_jahre if j != jahr_aktuell]
            jahr_vorjahr = st.selectbox(
                "Vergleichsjahr", options=jahr_vorjahr_optionen, index=0, key="jahresvergleich_vorjahr"
            )

        agg = (
            jahresvergleich_df[
                jahresvergleich_df["Anschaffungsjahr"].isin([jahr_aktuell, jahr_vorjahr])
            ]
            .groupby([dimension_spalte_jv, "Anschaffungsjahr"])
            .agg(
                Medien=("NR Zugang", "nunique"),
                Kosten=("Preis", "sum"),
                Ausleihen=("Ausleihen", "sum"),
            )
            .reset_index()
        )
        agg["Ausleihen pro Medium"] = np.where(
            agg["Medien"] > 0, agg["Ausleihen"] / agg["Medien"], 0
        )
        agg["Jahr"] = agg["Anschaffungsjahr"].astype(str)

        kennzahl_jv = st.selectbox(
            "Kennzahl",
            options=["Kosten", "Medien", "Ausleihen", "Ausleihen pro Medium"],
            key="jahresvergleich_kennzahl"
        )

        achsen_titel_jv = {
            "Kosten": "Kosten (CHF)",
            "Medien": "Anzahl Medien",
            "Ausleihen": "Anzahl Ausleihen",
            "Ausleihen pro Medium": "Ø Ausleihen pro Medium",
        }

        # --------------------------------------------------------
        # GRUPPIERTER BALKENVERGLEICH (nach Gesamtwert sortiert)
        # --------------------------------------------------------
        balken = (
            alt.Chart(agg)
            .mark_bar()
            .encode(
                x=alt.X(f"{dimension_spalte_jv}:N", title=dimension_label_jv.split(" ", 1)[-1], sort="-y"),
                xOffset="Jahr:N",
                y=alt.Y(f"{kennzahl_jv}:Q", title=achsen_titel_jv[kennzahl_jv], aggregate="sum"),
                color=alt.Color(
                    "Jahr:N", scale=alt.Scale(range=["#B0B8C1", "#4C78A8"]), title="Jahr"
                ),
                tooltip=[
                    alt.Tooltip(f"{dimension_spalte_jv}:N", title=dimension_label_jv.split(" ", 1)[-1]),
                    alt.Tooltip("Jahr:N", title="Jahr"),
                    alt.Tooltip("Medien:Q", title="Medien"),
                    alt.Tooltip("Kosten:Q", title="Kosten (CHF)", format=",.0f"),
                    alt.Tooltip("Ausleihen:Q", title="Ausleihen"),
                    alt.Tooltip("Ausleihen pro Medium:Q", title="Ø Ausleihen/Medium", format=".1f"),
                ],
            )
            .properties(height=420)
        )

        st.altair_chart(balken, use_container_width=True)




# ============================================================
# 📄 PDF-EXPORT
# ============================================================
st.divider()
st.subheader("📄 Bericht exportieren")
st.caption(
    "Erstellt ein PDF mit den aktuellen Kennzahlen sowie dem Lieferanten-, "
    "Vergleichs- und Jahresvergleich-Diagramm (berücksichtigt Ihre aktuelle "
    "Filter- und Diagrammauswahl)."
)

if st.button("📄 PDF erstellen", key="pdf_erstellen_button"):
    with st.spinner("PDF wird erstellt..."):
        kpis_fuer_pdf = {
            "Neuanschaffungen": (
                f"{anzahl_neu:,}".replace(",", "'")
                + f"\n{vorjahr}: {kpis_vorjahr['media_count']:,}".replace(",", "'")
                + f"\n{format_pdf_delta(anzahl_neu, kpis_vorjahr['media_count'])}"
            ),
            "Gesamtkosten": (
                f"CHF {gesamtkosten:,.0f}".replace(",", "'")
                + f"\n{vorjahr}: CHF {kpis_vorjahr['total_cost']:,.0f}".replace(",", "'")
                + f"\n{format_pdf_delta(gesamtkosten, kpis_vorjahr['total_cost'])}"
            ),
            "Ø Preis": (
                f"CHF {durchschnittspreis:,.2f}".replace(",", "'")
                + f"\n{vorjahr}: CHF {kpis_vorjahr['avg_price']:,.2f}".replace(",", "'")
                + f"\n{format_pdf_delta(durchschnittspreis, kpis_vorjahr['avg_price'])}"
            ),
            "Ausleihen": (
                f"{gesamtausleihen:,}".replace(",", "'")
                + f"\n{vorjahr}: {kpis_vorjahr['loan_count']:,}".replace(",", "'")
                + f"\n{format_pdf_delta(gesamtausleihen, kpis_vorjahr['loan_count'])}"
            ),
            "Ø Ausl./Medium": (
                f"{durchschnittliche_ausleihen:.1f}"
                + f"\n{vorjahr}: {kpis_vorjahr['avg_loans']:.1f}"
                + f"\n{format_pdf_delta(durchschnittliche_ausleihen, kpis_vorjahr['avg_loans'])}"
            ),
        }

        pdf_charts = []

        # ----------------------------------------------------
        # Ausgaben nach Lieferant (Top 10) – unabhängig von der
        # aktuellen Tab-Auswahl, damit immer im Bericht enthalten
        # ----------------------------------------------------
        top_lieferanten_df = (
            df_new.groupby("Lieferant")["Preis"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .reset_index()
            .rename(columns={"Preis": "Kosten"})
        )
        pdf_charts.append((
            "Ausgaben nach Lieferant (Top 10)",
            sortierter_balken(top_lieferanten_df, "Lieferant", "Kosten", "Lieferant", "Kosten (CHF)")
        ))

        # ----------------------------------------------------
        # Aktuelle Auswahl aus Tab "Vergleiche"
        # ----------------------------------------------------
        pdf_charts.append((
            f"Vergleich nach {dimension_label.split(' ', 1)[-1]} ({diagramm_art})",
            sortierter_balken(
                vergleich, "Vergleich", diagramm_art,
                dimension_label.split(" ", 1)[-1], achsen_titel[diagramm_art]
            )
        ))

        # ----------------------------------------------------
        # Jahresvergleich, falls verfügbar
        # ----------------------------------------------------
        if len(verfuegbare_jahre) >= 2:
            pdf_charts.append((
                f"Jahresvergleich {jahr_vorjahr} vs. {jahr_aktuell} "
                f"nach {dimension_label_jv.split(' ', 1)[-1]}",
                balken
            ))

        report = build_report_pdf(
            title="Medien Analyse - Bericht",
            subtitle=(
                "Kompakter Auszug der aktuellen Medien- und Neuzugangs-Auswertung."
            ),
            kpis=kpis_fuer_pdf,
            filters=build_media_filter_summary(filter_state),
            charts=pdf_charts,
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
        file_name=f"medien_analyse_{datetime.now():%Y%m%d_%H%M}.pdf",
        mime="application/pdf",
    )


# ============================================================
# ℹ️ GEMEINSAME ERKLÄRUNG (einmalig für beide Vergleichs-Tabs)
# ============================================================
with st.expander("ℹ️ Was bedeuten die Kennzahlen?"):
    st.markdown(
        """
**Medien**
Anzahl der unterschiedlichen angeschafften Medien.

**Kosten**
Summe der Preise aller angeschafften Medien.

**Ø Preis**
Durchschnittlicher Einkaufspreis eines Mediums.

**Ausleihen**
Gesamtzahl der Ausleihen dieser Neuanschaffungen.

**Ø Ausleihen / Medium**
Wie häufig ein durchschnittlich angeschafftes Medium ausgeliehen wurde.

**Ausleihen / CHF 100**
Zeigt die Nutzung im Verhältnis zu den Anschaffungskosten.

Beispiel: **5 Ausleihen / CHF 100** bedeutet, dass auf je CHF 100
Anschaffungskosten durchschnittlich fünf Ausleihen entfallen.

Diese Kennzahl eignet sich besonders gut, um unterschiedliche
Medienarten, Lesealter, Standorte oder Lieferanten miteinander zu vergleichen.
"""
    )
