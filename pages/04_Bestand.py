import streamlit as st
import pandas as pd
import altair as alt
import numpy as np

from src.filters import get_sidebar_filters
from components.ui import show_media_detail, kpi_box
from src.bestand_analysis import berechne_bestand_mit_reihen



st.set_page_config(
    page_title="Bestandsanalyse",
    page_icon="📦",
    layout="wide"
)



col1, col2 = st.columns([3,2])
with col1:
    st.title("📦 Bestandsanalyse")



st.sidebar.info(
    "ℹ️ Für einen schnellen Einstieg wurden Standardfilter gesetzt. "
    "Ändern oder entfernen Sie die Filter, um andere Bereiche des Bestands zu analysieren. "
    "Achtung: Wenn die Anzeige des Gesamtbestands braucht mehr Ladezeit."
)
# =====================================================
# DATEN LADEN
# =====================================================

if "data" not in st.session_state:
    st.error("Keine Daten geladen.")
    st.stop()
if "selected_medium" not in st.session_state:
    st.session_state['selected_medium'] = None
st.session_state.setdefault("selected_nr", None)
st.session_state.setdefault("selection_source", None)
if "table_key" not in st.session_state:
    st.session_state.table_key=0

data = st.session_state["data"]

df_loans = data.get("loans")
df_books = data.get("catalog")


if df_loans is None or df_books is None:
    st.error("Ausleih- oder Katalogdaten fehlen.")
    st.stop()

# =====================================================
# SPALTEN-DUPLIKATE BEREINIGEN
# =====================================================

if "Medienart" not in df_loans.columns and "Medienart_catalog" in df_loans.columns:
    df_loans["Medienart"] = df_loans["Medienart_catalog"]
if "Kategorie Alter" not in df_loans.columns and "Kategorie Alter_catalog" in df_loans.columns:
    df_loans["Kategorie Alter"] = df_loans["Kategorie Alter_catalog"]

# =====================================================
# FILTER
# =====================================================

extra_filters_config = [
    {"label": "📍 Standort", "col": "Standort(1)", "default":[]},
    {"label": "📚 Medienart", "col": "Medienart", "default":[]},
    {"label": "👶 Lesealter", "col": "Kategorie Alter", "default":[0]},
]

# Filter anwenden, hier keine Zeitfilter, da nicht relevant

_, df_loans_filtered, filter_info = get_sidebar_filters(
    df_users=None,
    df_extra=df_loans,
    prefix="bestand",
    enable_date_filter=False,
    date_col_name="Ausleihdatum",
    extra_filters_config=extra_filters_config,
    enable_first_loan_toggle=False,
    show_metrics=False
)

# Aktuellen Filterzustand merken
aktueller_filterzustand = tuple(
    (
        conf['col'],
        tuple(sorted(st.session_state.get(f"bestand_extra_{conf['col']}", [])))
    )
    for conf in extra_filters_config
)

# Hat sich seit dem letzten Run etwas geändert?
alter_filterzustand = st.session_state.get('bestand_filterzustand')

if (
    alter_filterzustand is not None
    and alter_filterzustand != aktueller_filterzustand
):
    st.session_state['bestand_suche']=""
st.session_state['bestand_filterzustand']=aktueller_filterzustand

key = "NR Zugang"

if key not in df_loans.columns:
    st.error("NR Zugang fehlt in den Ausleihdaten.")
    st.stop()

if key not in df_books.columns:
    st.error("NR Zugang fehlt im Katalog.")
    st.stop()




df_bestand_full = berechne_bestand_mit_reihen(df_books, df_loans)


df_bestand = df_bestand_full.copy()

if extra_filters_config:
    for conf in extra_filters_config:
        spalte = conf["col"]
        werte = st.session_state.get(f"bestand_extra_{spalte}", [])

        if werte and spalte in df_bestand.columns:
            df_bestand = df_bestand[df_bestand[spalte].astype(str).isin(werte)]


# Metrik für die Sidebar
anzahl_medien_im_plot = df_bestand["NR Zugang"].nunique()

with st.sidebar:
    st.metric(
        label="📊 Medien im Diagramm",
        value=f"{anzahl_medien_im_plot:,}",
        help="Enthält den gesamten gefilterten Bestand, auch Medien ohne Ausleihen."
    )


# =====================================================
# BEREINIGUNGS-SCHWELLENWERTE (INTUITIV, PROZENTBASIERT)
# =====================================================
# Statt abstrakter Score-Zahlen arbeiten die Regler jetzt mit Prozent-
# Angaben ("die schwächsten X % des Bestands"). Vorteil gegenüber den
# alten Score-Reglern: der Wertebereich ist immer fest 0-100 % und ändert
# sich nie durch einen Filterwechsel - der frühere Fehler, bei dem ein
# gespeicherter Regler-Wert nach einem Filterwechsel ausserhalb des neuen
# Score-Maximums lag (und Streamlit dadurch eine Exception warf, die sich
# wie ein Hänger anfühlte), kann so nicht mehr auftreten.
if st.session_state.pop("reset_bestand", False):
    st.session_state["bestand_schwelle_basis"] = "🔍 Aktuelle Filterung (lokal)"
    st.session_state["bestand_schwelle_pct"] = (80, 95)
with col2:
    with st.expander("🎚️ Bereinigungs-Schwellenwerte anpassen", expanded=False):

        st.caption(
            "Lege fest, ab welchem Anteil der schwächsten Medien (nach "
            "Bereinigungsscore) eine Kategorie beginnt."
        )

        basis_wahl = st.radio(
            "Basis für die Prozent-Berechnung",
            options=["🔍 Aktuelle Filterung (lokal)", "🌐 Gesamter Bestand (global)"],
            horizontal=True,
            key="bestand_schwelle_basis",
            help=(
                "Lokal: Prozent beziehen sich nur auf den aktuell gefilterten "
                "Standort/Medienart/Lesealter. Global: Prozent beziehen sich "
                "immer auf den kompletten, ungefilterten Bestand - praktisch, "
                "wenn die Schwellenwerte über verschiedene Filteransichten "
                "hinweg vergleichbar bleiben sollen."
            )
        )

        basis_df = df_bestand if basis_wahl.startswith("🔍") else df_bestand_full

        # Zeigt an, welche Filterwerte konkret in die gewählte Basis einfliessen -
        # gerade bei "lokal" sonst nicht auf den ersten Blick ersichtlich.
        aktive_filter_texte = []
        for conf in extra_filters_config:
            spalte = conf["col"]
            werte = st.session_state.get(f"bestand_extra_{spalte}", [])
            if werte:
                aktive_filter_texte.append(f"{conf['label']}: {', '.join(map(str, werte))}")

        if basis_wahl.startswith("🔍"):
            if aktive_filter_texte:
                st.caption("📌 Verwendete Filterwerte: " + " · ".join(aktive_filter_texte))
            else:
                st.caption("📌 Aktuell ist kein Filter gesetzt - 'lokal' entspricht daher dem gesamten Bestand.")
        else:
            st.caption("📌 Basis ist der gesamte Bestand, unabhängig von den Sidebar-Filtern.")

        if st.button(
            "🔄 Auf Standardwerte zurücksetzen",
            help="Setzt den Regler auf 80 % / 95 % zurück."
        ):
            st.session_state["reset_bestand"] = True
            st.rerun()

        # Eine einzelne Skala mit zwei Reglerpunkten statt zwei getrennter
        # Slider - st.slider gibt bei einem Tupel als value automatisch einen
        # Bereichs-Slider mit zwei Griffen zurück.
        pct_gruen, pct_rot = st.slider(
            "🟢 behalten → 🟡 prüfen → 🔴 Bereinigung prüfen",
            min_value=0, max_value=100, value=(80, 95), step=1,
            format="%d%%",
            key="bestand_schwelle_pct",
            help=(
                "Linker Punkt: Grenze 🟢→🟡. Rechter Punkt: Grenze 🟡→🔴. "
                "Beide als Anteil der schwächsten Medien (nach Bereinigungsscore)."
            )
        )

        if not basis_df.empty:
            schwelle_gruen = float(basis_df["Bereinigungsscore"].quantile(pct_gruen / 100))
            schwelle_rot = float(basis_df["Bereinigungsscore"].quantile(pct_rot / 100))
        else:
            schwelle_gruen, schwelle_rot = 0.0, 0.0

        # Mindestabstand, damit pd.cut keine doppelten Bin-Grenzen bekommt
        schwelle_rot_sicher = max(schwelle_rot, schwelle_gruen + 0.1)

        st.caption(
            f"Entspricht Score {schwelle_gruen:.1f} bzw. {schwelle_rot:.1f} "
            f"(Basis: {basis_wahl.split(' ', 1)[1]})."
        )
        st.info(
            f"Reihenschwellen: "
            f"gut ≤ {basis_df["Bereinigungsscore"].quantile(0.33)}, \n"
            f"wenig genutzt ≥ {basis_df["Bereinigungsscore"].quantile(0.66)}, "
            f"Abweichung ±{0.5 * basis_df["Bereinigungsscore"].std()}"
        )
        # --- Live-Vorschau: wie viele Medien landen in welcher Kategorie? ---
        if not df_bestand.empty:
            n_gruen = (df_bestand["Bereinigungsscore"] <= schwelle_gruen).sum()
            n_gelb = (
                (df_bestand["Bereinigungsscore"] > schwelle_gruen)
                & (df_bestand["Bereinigungsscore"] <= schwelle_rot_sicher)
            ).sum()
            n_rot = (df_bestand["Bereinigungsscore"] > schwelle_rot_sicher).sum()

            st.markdown(
                f"**Vorschau (aktuelle Filterung):** "
                f"🟢 {n_gruen:,} behalten · 🟡 {n_gelb:,} prüfen · "
                f"🔴 {n_rot:,} Bereinigung prüfen"
            )


df_bestand["Bereinigung"] = pd.cut(
    df_bestand["Bereinigungsscore"],
    bins=[-1, schwelle_gruen, schwelle_rot_sicher, float("inf")],
    labels=["🟢 behalten", "🟡 prüfen", "🔴 Bereinigung prüfen"]
)

bereinigung = (df_bestand["Bereinigung"] == "🔴 Bereinigung prüfen").sum()


# =====================================================
# KENNZAHLEN
# =====================================================

c1, c2, c3, c4, c5 = st.columns(5)

behalten = (df_bestand["Bereinigung"] == "🟢 behalten").sum()
pruefen = (df_bestand["Bereinigung"] == "🟡 prüfen").sum()
bereinigung = (df_bestand["Bereinigung"] == "🔴 Bereinigung prüfen").sum()
score_mean = df_bestand["Bereinigungsscore"].mean()

with c1:
    kpi_box("📚 Bestand", f"{len(df_bestand):,}")
with c2:
    kpi_box("🟢 behalten", f"{behalten:,}")
with c3:
    kpi_box("🟡 prüfen", f"{pruefen:,}")
with c4:
    kpi_box("🔴 Bereinigung", f"{bereinigung:,}")
with c5:
    kpi_box("⭐ Ø Score", f"{score_mean:.1f}")
st.divider()
# =====================================================
# PORTFOLIO-ANALYSE: ALTER VS. NUTZUNG
# =====================================================

farben = {
    "🟢 behalten": "#2ca02c",
    "🟡 prüfen": "#f1c40f",
    "🔴 Bereinigung prüfen": "#e74c3c",
}
col1, col2 = st.columns([3,2])
with col1: 
    st.subheader("📈 Bestandsportfolio: Alter vs. Nutzung")

scatter_data = df_bestand.copy()
scatter_data = scatter_data[scatter_data["Alter_Jahre"].notna()]
scatter_data = scatter_data[scatter_data["Umlauf"].notna()]

# Nur die für Chart/Detailkarte benötigten Spalten mitgeben.
# df_bestand schleppt sonst alle ~100 Original-Katalogspalten mit , was beim Serialisieren fürs Chart
# zu einem ArrowInvalid-Fehler führt.
benoetigte_spalten = [
    "NR Zugang",
    "Titel",
    "Verfasser I(1)",
    "Kategorie Alter",
    "Reihe(1)",
    "Band",
    "Reihen_Anzahl_Baende",
    "Reihen_Median_Score",
    "Reihen_Luecken",
    "Reihen_Hinweis",
    "Aufnahme_Monat_Jahr",
    "Standort(1)",
    "Medienart",
    "Alter_Jahre",
    "Umlauf",
    "Umlauf_365Tage",
    "Ausleihen_pro_Jahr",
    "Anzahl_Ausleihen",
    "Ausleihen_365Tage",
    "Bestand",
    "Score_Nutzung",
    "Score_Aktualitaet",
    "Score_Alter",
    "Score_Trend",
    "Bereinigungsscore",
    "Bereinigung",
    "URL_Cover",
    "Letzte_Ausleihe",
]
benoetigte_spalten = [c for c in benoetigte_spalten if c in scatter_data.columns]
scatter_data = scatter_data[benoetigte_spalten].copy()

if not scatter_data.empty:

    # Domain für die Legende IMMER aus den echten Kategorie-Werten ableiten,
    # damit Emoji/Text nie versehentlich von der Farbzuordnung abweichen kann.
    kategorien = [
        k for k in df_bestand["Bereinigung"].cat.categories.tolist()
        if k in scatter_data["Bereinigung"].unique().tolist()
    ] or df_bestand["Bereinigung"].cat.categories.tolist()


    range_farben = [farben[k] for k in kategorien]

    with col2:
        sichtbare_kategorien = st.multiselect(
            "Bereinigungskategorien anzeigen",
            options=kategorien,
            default =kategorien
        )
    scatter_data = scatter_data[
        scatter_data['Bereinigung'].isin(sichtbare_kategorien)
    ]
    # Fester Seed für reproduzierbaren Jitter (Punkte springen beim Zoomen nicht)
    np.random.seed(42)
    scatter_data["Alter_Jahre_Jitter"] = (
        scatter_data["Alter_Jahre"] + np.random.uniform(-0.1, 0.1, size=len(scatter_data))
    )
    scatter_data["Ausleihen_Jitter"] = (
        scatter_data["Anzahl_Ausleihen"] + np.random.uniform(-0.1, 0.1, size=len(scatter_data))
    )

    punkt_klick = alt.selection_point(
        fields=["NR Zugang"],
        name="punkt_klick",
        on="click",
        empty=False,
    )
    scatter_data['Reihe_Band'] = scatter_data.apply(
        lambda r: (
            f"{r['Reihe(1)']} (Band {r['Band']})"
            if pd.notna(r["Reihe(1)"]) and str(r["Reihe(1)"]).strip() != ""
            else None
        ),
        axis=1
    )
    scatter = (
        alt.Chart(scatter_data)
        .mark_circle(opacity=0.7, stroke="white", strokeWidth=0.5)
        .encode(
            x=alt.X("Alter_Jahre_Jitter:Q", title="Alter Medium (Jahre)"),
            y=alt.Y(
                "Ausleihen_Jitter:Q",
                title="Anzahl Ausleihen (gesamt)",
                axis=alt.Axis(format=".0f")
            ),
            size=alt.Size(
                "Bereinigungsscore:Q",
                title="Bereinigungsscore",
                scale=alt.Scale(range=[20, 500])
            ),
            color=alt.Color(
                "Bereinigung:N",
                title="Bewertung",
                scale=alt.Scale(domain=kategorien, range=range_farben)
            ),
            tooltip=[
                "Titel",
                alt.Tooltip("Verfasser I(1):N", title="Autor"),
                alt.Tooltip("Reihe_Band:N", title="Reihe"),
                alt.Tooltip("Standort(1):N", title="Standort"),
                "Medienart",
                "Kategorie Alter",
                "Aufnahme_Monat_Jahr",
                alt.Tooltip("Alter_Jahre:Q", title="Alter (exakt)", format=".1f"),
                alt.Tooltip("Anzahl_Ausleihen:Q", title="Ausleihen gesamt", format=".0f"),
                alt.Tooltip("Ausleihen_365Tage:Q", title="Ausleihen (letzte 365 Tage)", format=".0f"),
                "Bereinigungsscore",
                "Reihen_Hinweis"
            ]
        )
        .add_params(punkt_klick)
        .properties(height=350)
        .interactive()
    )

    event = st.altair_chart(
        scatter,
        width="stretch",
        on_select="rerun",
        key="bestand_scatter"
    )

    # --- Detailkarte für den angeklickten Punkt ---
    selektierte_nr = None

    if event and "selection" in event:
        punkte = event["selection"].get("punkt_klick", [])
        if punkte:
            selektierte_nr = punkte[0].get("NR Zugang")

    if selektierte_nr is not None:
        treffer = scatter_data[
            scatter_data["NR Zugang"]==selektierte_nr
        ]
        if not treffer.empty:
            st.session_state.selected_medium = treffer.iloc[0]
            st.session_state.selection_source = "scatter"

else:
    st.info("Keine ausreichenden Daten für Portfolioanalyse vorhanden.")

detail_placeholder = st.empty()  


# =====================================================
# TABELLE: NUR AUF ABFRUF (EXPANDER UNTEN)
# =====================================================
with st.expander("📋 Liste: Bereinigungskandidaten"):
    
    col1, col2, col3, col4 =st.columns([6,4,1,1])
    with col1:
        st.caption(
            "Hier finden Sie die Medien mit dem höchsten Bereinigungspotenzial sortiert nach Score."
            "Für Details klicken Sie bitte auf den Punkt im Diagramm."
        )

    score = df_bestand.sort_values("Bereinigungsscore", ascending=False)
    
    with col2:
        suche = st.text_input("🔍 Medium suchen", key='bestand_suche')

        if suche:
            if suche.isdigit():
                score=df_bestand_full[
                    df_bestand_full['NR Zugang'].astype(str)==suche
                ]
            else:
                maske = (
                    score["Titel"].astype(str).str.contains(suche, case=False, na=False)
                    |
                    score["Verfasser I(1)"].astype(str).str.contains(suche, case=False, na=False)
                    |
                    score["Medienart"].astype(str).str.contains(suche, case=False, na=False)
                    |
                    score["Signatur Klartext"].astype(str).str.contains(suche, case=False, na=False)
                    |
                    score['Reihe(1)'].astype(str).str.contains(suche, case=False, na=False)
                )

                score = score[maske]


    with col3:
        page_size = st.selectbox(
            "Zeilen pro Seite",
            [25,50,100,250],
            index=1
        )
    with col4:
        pages = max(1, (len(score)-1) // page_size + 1)

        page = st.number_input(
            "Seite",
            min_value=1,
            max_value=pages,
            value=1
        )

    start = (page-1)*page_size
    ende = start + page_size

    spalten = [
        "Medienart",
        "Signatur(1)",
        "NR Zugang",
        "Titel",
        "Verfasser I(1)",
        "Kategorie Alter",
        "Reihe(1)",
        "Band",
        "Aufnahme_Monat_Jahr",
        "Alter_Jahre",
        "Standort(1)",
        "Anzahl_Ausleihen",
        "Ausleihen_pro_Jahr",
        "Ausleihen_365Tage",
        "Bereinigungsscore",
        "Bereinigung",
        "Reihen_Hinweis",
        #"Umlauf",
        #"Umlauf_365Tage",
        "Score_Nutzung",
        "Score_Aktualitaet",
        "Score_Alter",
        "Score_Trend"

    ]
    spalten = [c for c in spalten if c in score.columns]
    page_df = score.iloc[start:ende]
    event=st.dataframe(
        page_df[spalten], 
        key =f"bereinigung_{st.session_state.table_key}",
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row")
    if event.selection.rows:
        index = start + event.selection.rows[0]
        st.session_state.selected_medium = score.iloc[index]

        st.session_state.table_key +=1

    
    st.caption(f"Zeige {start+1}-{min(ende,len(score))} von {len(score)} Datensätzen")

with detail_placeholder.container():
    if st.session_state.get("selected_medium") is not None:
        show_media_detail(st.session_state["selected_medium"], farben)
    else:
        st.info('👉 Klicken Sie auf einen Punkt im Diagramm oder wählen Sie ein Medium in der Tabelle aus, um die Detailansicht zu öffnen.')



with st.expander("ℹ️ Bewertungslogik der Bestandsanalyse"):

    st.markdown("""
Die Bestandsanalyse bewertet jedes Medium anhand mehrerer Kriterien und berechnet daraus einen
**Bereinigungsscore (0–100 Punkte)**.

Ein **hoher Score** bedeutet, dass ein Medium eher als Bereinigungskandidat in Frage kommt.

### Zusammensetzung des Bereinigungsscores

| Komponente | Max. Punkte | Bedeutung |
|---|---:|---|
| **Nutzungsintensität** | 35 | Wenige Ausleihen pro Jahr → mehr Punkte |
| **Aktualität** | 30 | Lange keine Ausleihe → mehr Punkte |
| **Alter** | 15 | Älteres Medium → mehr Punkte |
| **Nutzungstrend** | 20 | Früher häufig genutzt, in letzter Zeit deutlich weniger → mehr Punkte |

Alle Teilwerte werden **kontinuierlich** berechnet. Dadurch entstehen keine festen Scoreklassen, sondern eine nachvollziehbare Bewertung jedes einzelnen Mediums.

---

### Bereinigungskategorien

Die Einteilung erfolgt **nicht über feste Scorewerte**, sondern über den Anteil der Medien mit den höchsten Bereinigungsscores.

**Standardmässig gelten:**

- 🟢 **behalten:** unterste **80 %** der Scores
- 🟡 **prüfen:** höchste **20 %** der Scores
- 🔴 **Bereinigung prüfen:** höchste **5 %** der Scores

Über **„🎚️ Bereinigungs-Schwellenwerte anpassen“** können diese Prozentwerte jederzeit verändert werden.

Dabei stehen zwei Berechnungsgrundlagen zur Verfügung:

- **🔍 Aktuelle Filterung (lokal):** Die Prozentwerte beziehen sich nur auf die aktuell gefilterten Medien.
- **🌐 Gesamter Bestand (global):** Die Prozentwerte beziehen sich immer auf den gesamten Bestand und bleiben dadurch zwischen verschiedenen Filterungen vergleichbar.

---

### Verwendete Kennzahlen

Für die Bewertung werden mehrere Kennzahlen kombiniert:

- **Ausleihen gesamt**
- **Ausleihen pro Jahr** (altersbereinigt)
- **Ausleihen der letzten 365 Tage**
- **Jahre seit der letzten Ausleihe**
- **Alter des Mediums**

Dadurch werden sowohl ältere als auch neuere Medien möglichst fair bewertet. Ein älteres Medium wird also nicht allein wegen seines Alters als Bereinigungskandidat eingestuft, sondern nur dann, wenn zusätzlich eine geringe oder rückläufige Nutzung vorliegt.

---

### Nachvollziehbarkeit

Die einzelnen Teil-Scores (**Nutzung**, **Aktualität**, **Alter** und **Trend**) werden in der Detailansicht eines Mediums sowie in der Tabelle angezeigt. Dadurch lässt sich jederzeit nachvollziehen, warum ein Medium einen bestimmten Bereinigungsscore erhalten hat.
""")
