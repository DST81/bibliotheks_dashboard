import streamlit as st
import pandas as pd
import altair as alt
from filters import get_sidebar_filters
import numpy as np
import time

_start_zeit = time.perf_counter()

st.set_page_config(
    page_title="Bestandsanalyse",
    page_icon="📦",
    layout="wide"
)


def _log_zeit(schritt: str, dauer: float) -> None:
    """
    Schreibt Zeitmessungen zusätzlich ins Server-Terminal (dort, wo
    `streamlit run` läuft) - unabhängig von der Debug-Checkbox in der UI.
    Wichtig, weil das Anklicken der Checkbox selbst schon einen Rerun
    auslöst und damit den Cache "aufwärmt" - der wirklich interessante,
    allererste (kalte) Aufruf dieser Seite nach einem App-Neustart wird
    dadurch in der UI-Anzeige verpasst, taucht hier im Terminal aber auf.
    """
    print(f"[Bestandsanalyse] {schritt}: {dauer:.2f}s")
    verlauf = st.session_state.setdefault("bestand_ladezeiten_verlauf", [])
    verlauf.append(f"{schritt}: {dauer:.2f}s")
    st.session_state["bestand_ladezeiten_verlauf"] = verlauf[-20:]  # nur die letzten 20 behalten


st.title("📦 Bestandsanalyse")

debug_zeiten = st.sidebar.checkbox(
    "🐢 Ladezeiten anzeigen (Debug)",
    value=False,
    key="bestand_debug_zeiten",
    help="Zeigt in der Sidebar, wie lange die einzelnen Schritte brauchen - "
         "hilfreich, um den tatsächlichen Flaschenhals bei langsamem Start zu finden."
)

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


data = st.session_state["data"]

df_loans = data.get("loans")
df_books = data.get("catalog")


if df_loans is None or df_books is None:
    st.error("Ausleih- oder Katalogdaten fehlen.")
    st.stop()

# =====================================================
# SPALTEN-DUPLIKATE BEREINIGEN
# =====================================================
# df_loans stammt aus einem früheren Merge und enthält "Medienart" doppelt
# als "Medienart_x" / "Medienart_y". Für die Filter (extra_filters_config)
# brauchen wir eine eindeutige Spalte "Medienart" -> wir verwenden _x.
if "Medienart" not in df_loans.columns and "Medienart_x" in df_loans.columns:
    df_loans["Medienart"] = df_loans["Medienart_x"]
if "Kategorie Alter" not in df_loans.columns and "Kategorie Alter_x" in df_loans.columns:
    df_loans["Kategorie Alter"] = df_loans["Kategorie Alter_x"]

# =====================================================
# FILTER
# =====================================================

extra_filters_config = [
    {"label": "📍 Standort", "col": "Standort(1)", "default":[]},
    {"label": "📚 Medienart", "col": "Medienart", "default":[]},
    {"label": "👶 Lesealter", "col": "Kategorie Alter", "default":[0]},
]

# Filter anwenden, hier keine Zeitfilter, da nicht relevant
_t_filter = time.perf_counter()
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
_log_zeit("get_sidebar_filters()", time.perf_counter() - _t_filter)

key = "NR Zugang"

if key not in df_loans.columns:
    st.error("NR Zugang fehlt in den Ausleihdaten.")
    st.stop()

if key not in df_books.columns:
    st.error("NR Zugang fehlt im Katalog.")
    st.stop()


# =====================================================
# ROBUSTES, PERFORMANTES DATUMS-PARSING
# =====================================================
# Strategie: zuerst das/die erwartete(n) Format(e) exakt versuchen (das ist
# der schnelle, vektorisierte C-Pfad von pandas). NUR für die Werte, die
# dabei nicht geparst werden konnten, wird zusätzlich noch ein flexibler
# Parser-Versuch (dayfirst=True) unternommen - das betrifft normalerweise
# nur eine kleine Minderheit der Zeilen.
#
# Wichtig: format="mixed" oder dayfirst=True OHNE festes Format über die
# GESAMTE Spalte zwingt pandas dazu, jeden einzelnen Wert einzeln per
# dateutil zu parsen. Bei einem grossen Bibliotheksbestand (viele tausend
# Zeilen) kann das spürbar langsam werden bis hin zum gefühlten
# "Aufhängen" der App - das ist der wahrscheinlichste Kandidat für euer
# Problem, falls die Spalten uneinheitlich formatiert sind.
def erkenne_bestes_format(series: pd.Series, kandidaten: list, sample_size: int = 300):
    """
    Testet an einer kleinen Stichprobe, welches der Kandidaten-Formate am
    besten zur Spalte passt, und gibt dieses zurück (oder None, falls keins
    mindestens die Hälfte der Stichprobe erklärt).

    Wichtig für die Performance: OHNE diesen Schritt würde bei falsch
    geratenem Erstformat fast die GESAMTE Spalte im langsamen Fallback
    (zeilenweises dateutil-Parsing weiter unten) landen - dann bringt die
    ganze Format-Liste nichts. Die Stichprobe kostet nur Millisekunden,
    spart aber im schlechtesten Fall mehrere Sekunden bis Minuten beim
    Parsen der vollen Spalte.
    """
    werte = series.dropna().astype(str)
    werte = werte[werte.str.strip() != ""]
    if werte.empty:
        return None

    stichprobe = (
        werte.sample(sample_size, random_state=42) if len(werte) > sample_size else werte
    )

    bestes_format = None
    beste_quote = 0.0
    for fmt in kandidaten:
        quote = pd.to_datetime(stichprobe, format=fmt, errors="coerce").notna().mean()
        if quote > beste_quote:
            beste_quote = quote
            bestes_format = fmt

    return bestes_format if beste_quote >= 0.5 else None


def robustes_datum(series: pd.Series, formate) -> pd.Series:
    if series is None:
        return pd.Series(dtype="datetime64[ns]")

    s = series.copy()

    if pd.api.types.is_datetime64_any_dtype(s):
        return s

    if isinstance(formate, str):
        formate = [formate]

    # Bei nur einem Format-Kandidaten ist die Stichproben-Erkennung
    # überflüssig (z.B. "Datum der Aufnahme", dessen Format laut Bibliothek
    # fix bekannt ist) - direkt den schnellen Pfad nehmen.
    if len(formate) == 1:
        formate_sortiert = formate
    else:
        bestes_format = erkenne_bestes_format(s, formate)
        formate_sortiert = (
            [bestes_format] + [f for f in formate if f != bestes_format]
            if bestes_format else formate
        )

    ergebnis = pd.Series(pd.NaT, index=s.index)
    rest_maske = pd.Series(True, index=s.index)

    for fmt in formate_sortiert:
        if not rest_maske.any():
            break
        geparst = pd.to_datetime(s[rest_maske], format=fmt, errors="coerce")
        ergebnis.loc[rest_maske] = geparst
        rest_maske = ergebnis.isna()

    # Fallback nur für den kleinen Rest, der mit keinem Format passte
    if rest_maske.any():
        fallback = pd.to_datetime(s[rest_maske], errors="coerce", dayfirst=True)
        ergebnis.loc[rest_maske] = fallback

    return ergebnis


# =====================================================
# KERNBERECHNUNG - EINMAL FÜR DEN GESAMTEN KATALOG (GECACHT)
# =====================================================
# Der komplette Merge- und Score-Prozess hängt NICHT von den Sidebar-
# Filtern (Standort/Medienart/Lesealter) ab - die Filter wählen nur aus,
# WELCHE Zeilen am Ende angezeigt werden, ändern aber nicht, WIE der Score
# für ein einzelnes Medium berechnet wird. Deshalb berechnen wir ihn genau
# einmal für den kompletten Bestand und cachen das Ergebnis. Filter- oder
# Schwellenwert-Änderungen lösen danach nur noch ein schnelles Filtern in
# einem bereits fertigen DataFrame aus, statt bei jeder Slider-Bewegung
# den kompletten Merge+Score-Prozess (inkl. Datums-Parsing) neu laufen zu
# lassen. Das war vermutlich die Hauptursache für das "Aufhängen".
#
# hash_funcs={pd.DataFrame: id}: wir hashen die Eingabe-DataFrames nicht
# über ihren Inhalt (das wäre bei grossen Tabellen selbst schon teuer),
# sondern über ihre Objekt-Identität. Da df_books/df_loans einmal geladen
# und danach im gleichen Session-State-Objekt wiederverwendet werden,
# bleibt der Cache über Reruns hinweg gültig und wird nur neu berechnet,
# wenn tatsächlich neue Daten geladen werden.
@st.cache_data(show_spinner="Bestand wird analysiert ...", hash_funcs={pd.DataFrame: id})
def berechne_bestand_scores(df_books_all: pd.DataFrame, df_loans_all: pd.DataFrame) -> pd.DataFrame:

    df_bestand = df_books_all.copy()

    # --- Historische Ausleihen ---
    if "Ausleihen" in df_bestand.columns:
        df_bestand["Anzahl_Ausleihen"] = df_bestand["Ausleihen"].replace("", np.nan)
        df_bestand["Anzahl_Ausleihen"] = pd.to_numeric(
            df_bestand["Anzahl_Ausleihen"], errors="coerce"
        ).fillna(0)
        df_bestand["Anzahl_Ausleihen"] = df_bestand["Anzahl_Ausleihen"].astype(int)
    else:
        # FALLBACK: Falls die Spalte fehlt - über ALLE Ausleihen zählen
        # (bewusst ungefiltert, damit das Ergebnis unabhängig von den
        # Sidebar-Filtern bleibt und im Cache wiederverwendet werden kann).
        ausleihen_count = (
            df_loans_all
            .groupby("NR Zugang")
            .size()
            .reset_index(name="Anzahl_Ausleihen")
        )
        df_bestand = df_bestand.merge(ausleihen_count, on="NR Zugang", how="left")
        df_bestand["Anzahl_Ausleihen"] = df_bestand["Anzahl_Ausleihen"].fillna(0).astype(int)

    # --- Letzte Ausleihe ---
    # WICHTIG: Wir nutzen das Feld "letzte Ausleihe" direkt aus dem Katalog
    # (df_books), NICHT df_loans. df_loans enthält laut Bibliothek nur die
    # Ausleihen der letzten ca. 2 Jahre - ein Medium, das z.B. vor 4 Jahren
    # zuletzt ausgeliehen wurde, hätte dort gar keinen Eintrag mehr, obwohl
    # es sehr wohl schon mal ausgeliehen wurde. Das Katalogfeld wird bei
    # jeder Ausleihe aktualisiert und ist daher zuverlässiger.
    if "letzte Ausleihe" in df_bestand.columns:
        # Format ist laut Bibliothek fix "MM/DD/YYYY HH:MM:SS"
        # (z.B. "01/05/2021 18:44:33") - kein Erraten per Stichprobe nötig.
        df_bestand["Letzte_Ausleihe"] = robustes_datum(
            df_bestand["letzte Ausleihe"], ["%m/%d/%Y %H:%M:%S"]
        )
    else:
        df_bestand["Letzte_Ausleihe"] = pd.NaT

    # --- Ausleihen der letzten 365 Tage ---
    # Bewusst aus df_loans_all (ungefiltert), damit "letzte 365 Tage" immer
    # ein fixes, aktuelles Zeitfenster ist - unabhängig von Filtern.
    grenze_365 = pd.Timestamp.today() - pd.Timedelta(days=365)

    ausleihen_365 = (
        df_loans_all[df_loans_all["Ausleihdatum"] >= grenze_365]
        .groupby("NR Zugang")
        .size()
        .reset_index(name="Ausleihen_365Tage")
    )

    df_bestand = df_bestand.merge(ausleihen_365, on="NR Zugang", how="left")
    df_bestand["Ausleihen_365Tage"] = df_bestand["Ausleihen_365Tage"].fillna(0).astype(int)

    # --- Umlauf ---
    # TODO: Falls im Katalog eine echte Exemplar-Spalte existiert (z.B.
    # "Anz_Exemplare"), hier verwenden statt fix 1 zu setzen:
    # df_bestand["Bestand"] = df_bestand["Anz_Exemplare"]
    df_bestand["Bestand"] = 1
    df_bestand["Umlauf"] = df_bestand["Anzahl_Ausleihen"] / df_bestand["Bestand"]

    # --- Alter ---
    if "Datum der Aufnahme" in df_bestand.columns:
        # Format ist laut Bibliothek fix "MM/DD/YYYY" (z.B. "04/10/2001") -
        # kein Erraten per Stichprobe nötig, direkt der schnelle Pfad.
        df_bestand["Aufnahme_DT"] = robustes_datum(
            df_bestand["Datum der Aufnahme"], ["%m/%d/%Y"]
        )
    else:
        df_bestand["Aufnahme_DT"] = pd.NaT

    df_bestand["Alter_Jahre"] = (
        (pd.Timestamp.today() - df_bestand["Aufnahme_DT"]).dt.days.div(365).round(1)
    )

    # --- Zusätzliche, altersfaire / aktuelle Umlaufkennzahlen ---
    df_bestand["Ausleihen_pro_Jahr"] = np.where(
        df_bestand["Alter_Jahre"] >= 0.5,
        (df_bestand["Anzahl_Ausleihen"] / df_bestand["Alter_Jahre"]).round(2),
        np.nan
    )
    df_bestand["Umlauf_365Tage"] = (
        df_bestand["Ausleihen_365Tage"] / df_bestand["Bestand"]
    ).round(2)

    # --- Jahre seit letzter Ausleihe ---
    # Für nie ausgeliehene Medien: Alter des Mediums selbst verwenden.
    df_bestand["Jahre_seit_letzter_Ausleihe"] = (
        (pd.Timestamp.today() - df_bestand["Letzte_Ausleihe"]).dt.days / 365
    )
    df_bestand["Jahre_seit_letzter_Ausleihe"] = df_bestand[
        "Jahre_seit_letzter_Ausleihe"
    ].fillna(df_bestand["Alter_Jahre"])

    # --- Score-Komponente 1: Nutzungsintensität (max. 35) ---
    rate_pro_jahr = pd.Series(
        np.where(
            df_bestand["Alter_Jahre"] >= 0.5,
            df_bestand["Ausleihen_pro_Jahr"].fillna(0),
            df_bestand["Umlauf_365Tage"]
        ),
        index=df_bestand.index
    )
    df_bestand["Score_Nutzung"] = (
        35 * (1 - (rate_pro_jahr / 1.0)).clip(lower=0, upper=1)
    ).round(1)

    # --- Score-Komponente 2: Aktualität (max. 30) ---
    df_bestand["Score_Aktualitaet"] = (
        6 * df_bestand["Jahre_seit_letzter_Ausleihe"]
    ).clip(lower=0, upper=30).round(1)

    # --- Score-Komponente 3: Alter (max. 15) ---
    df_bestand["Score_Alter"] = (
        1.5 * df_bestand["Alter_Jahre"].fillna(0)
    ).clip(lower=0, upper=15).round(1)

    # --- Score-Komponente 4: Trend "abgestürzt" (max. 20) ---
    rate_sicher = rate_pro_jahr.where(rate_pro_jahr > 0, np.nan)
    verhaeltnis_aktuell = (df_bestand["Umlauf_365Tage"] / rate_sicher).clip(upper=1)
    trend_rohwert = (20 * (1 - verhaeltnis_aktuell)).clip(lower=0, upper=20)
    df_bestand["Score_Trend"] = np.where(
        rate_pro_jahr >= 0.2, trend_rohwert.fillna(0), 0
    ).round(1)

    # --- Gesamtscore ---
    df_bestand["Bereinigungsscore"] = (
        df_bestand["Score_Nutzung"]
        + df_bestand["Score_Aktualitaet"]
        + df_bestand["Score_Alter"]
        + df_bestand["Score_Trend"]
    ).round(1)

    # --- Nutzungsstatus ---
    def status_bewertung(umlauf):
        if umlauf == 0:
            return "🔴 Ladenhüter"
        elif umlauf < 0.2:
            return "🟠 Kritisch"
        elif umlauf < 1:
            return "🟡 Beobachten"
        else:
            return "🟢 Aktiv"

    df_bestand["Status"] = df_bestand["Umlauf"].apply(status_bewertung)

    # --- Aufnahme-Monat/Jahr, deutsch formatiert ---
    monats_map = {
        "January": "Januar", "February": "Februar", "March": "März", "April": "April",
        "May": "Mai", "June": "Juni", "July": "Juli", "August": "August",
        "September": "September", "October": "Oktober", "November": "November",
        "December": "Dezember"
    }
    monat_jahr = df_bestand["Aufnahme_DT"].dt.strftime("%B %Y")
    df_bestand["Aufnahme_Monat_Jahr"] = monat_jahr.apply(
        lambda x: monats_map.get(x.split()[0], x.split()[0]) + " " + x.split()[1]
        if pd.notna(x) else ""
    )
    df_bestand.loc[df_bestand["Aufnahme_DT"].isna(), "Aufnahme_Monat_Jahr"] = ""

    return df_bestand


_t_scores = time.perf_counter()
df_bestand_full = berechne_bestand_scores(df_books, df_loans)
_dauer_scores = time.perf_counter() - _t_scores
_log_zeit("berechne_bestand_scores()", _dauer_scores)
if debug_zeiten:
    st.sidebar.caption(
        f"⏱️ Score-Berechnung: {_dauer_scores:.2f}s "
        f"(sehr schnell = Cache-Treffer, mehrere Sekunden = tatsächliche Neuberechnung)"
    )


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

c1.metric("📚 Bestand", f"{len(df_bestand):,}")
c2.metric("🟢 behalten", f"{behalten:,}")
c3.metric("🟡 prüfen", f"{pruefen:,}")
c4.metric("🔴 Bereinigung", f"{bereinigung:,}")
c5.metric("⭐ Ø Score", f"{score_mean:.1f}")


# =====================================================
# PORTFOLIO-ANALYSE: ALTER VS. NUTZUNG
# =====================================================

st.subheader("📈 Bestandsportfolio: Alter vs. Nutzung")

scatter_data = df_bestand.copy()
scatter_data = scatter_data[scatter_data["Alter_Jahre"].notna()]
scatter_data = scatter_data[scatter_data["Umlauf"].notna()]

# Nur die für Chart/Detailkarte benötigten Spalten mitgeben.
# df_bestand schleppt sonst alle ~100 Original-Katalogspalten mit (u.a.
# "Band" mit gemischten Typen int/"" ), was beim Serialisieren fürs Chart
# zu einem ArrowInvalid-Fehler führt.
benoetigte_spalten = [
    "NR Zugang",
    "Titel",
    "Verfasser I(1)",
    "Kategorie Alter",
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

    farben = {
        "🟢 behalten": "#2ca02c",
        "🟡 prüfen": "#f1c40f",
        "🔴 Bereinigung prüfen": "#e74c3c",
    }
    range_farben = [farben[k] for k in kategorien]

    st.caption("Medien rechts unten sind alt und wenig genutzt → mögliche Bereinigungskandidaten. ")
    st.caption("👉 Klicke auf einen Punkt, um Details inkl. Cover zu sehen.")

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
                "Standort(1)",
                "Medienart",
                "Kategorie Alter",
                "Aufnahme_Monat_Jahr",
                alt.Tooltip("Alter_Jahre:Q", title="Alter (exakt)", format=".1f"),
                alt.Tooltip("Anzahl_Ausleihen:Q", title="Ausleihen gesamt", format=".0f"),
                alt.Tooltip("Ausleihen_365Tage:Q", title="Ausleihen (letzte 365 Tage)", format=".0f"),
                "Bereinigungsscore"
            ]
        )
        .add_params(punkt_klick)
        .properties(height=500)
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
        treffer = scatter_data[scatter_data["NR Zugang"] == selektierte_nr]

        if not treffer.empty:
            buch = treffer.iloc[0]
            bewertung = buch.get("Bereinigung", None)
            badge_farbe = farben.get(bewertung, "#888888")

            letzte_ausleihe_dt = buch.get("Letzte_Ausleihe", pd.NaT)
            if pd.notna(letzte_ausleihe_dt):
                letzte_ausleihe_text = pd.Timestamp(letzte_ausleihe_dt).strftime("%d.%m.%Y")
            else:
                letzte_ausleihe_text = "unbekannt"

            st.divider()

            with st.container(border=True):

                col_bild, col_info = st.columns([1, 2.6], gap="medium")

                with col_bild:
                    cover_url = buch.get("URL_Cover", "")
                    if cover_url and str(cover_url).strip():
                        st.image(str(cover_url), width=170)
                    else:
                        st.markdown(
                            "<div style='width:170px;height:230px;"
                            "background:#f0f0f0;border-radius:8px;"
                            "display:flex;align-items:center;justify-content:center;"
                            "color:#999;font-size:0.85em;text-align:center;'>"
                            "📕<br>Kein Cover</div>",
                            unsafe_allow_html=True
                        )

                with col_info:
                    st.markdown(f"#### {buch.get('Titel', '-')}")
                    autor = buch.get("Verfasser I(1)", "")
                    if autor and str(autor).strip():
                        st.markdown(f"<span style='color:#666;'>{autor}</span>", unsafe_allow_html=True)

                    st.markdown(
                        f"<span style='background-color:{badge_farbe}22; "
                        f"color:{badge_farbe}; padding:4px 12px; border-radius:14px; "
                        f"font-size:0.85em; font-weight:600;'>{bewertung}</span>"
                        f"&nbsp;&nbsp;"
                        f"<span style='color:#888; font-size:0.85em;'>"
                        f"📍 {buch.get('Standort(1)', '-')} &nbsp;·&nbsp; "
                        f"📚 {buch.get('Medienart', '-')} &nbsp; &nbsp; "
                        f"📅 {buch.get('Aufnahme_Monat_Jahr', '-')} &nbsp; &nbsp; "
                        f"👶 {buch.get('Kategorie Alter', '-')}"
                        f"</span>",
                        unsafe_allow_html=True
                    )

                    st.write("")

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Alter", f"{buch.get('Alter_Jahre', '-')} J.")
                    m2.metric("Ausleihen gesamt", f"{buch.get('Anzahl_Ausleihen', '-')}")
                    m3.metric("Letzte 365 Tage", f"{buch.get('Ausleihen_365Tage', '-')}")
                    m4.metric("Score", f"{buch.get('Bereinigungsscore', '-')}")

                    st.caption(f"🕓 Letzte Ausleihe: {letzte_ausleihe_text}")

                    st.markdown(
                        f"<span style='color:#888; font-size:0.8em;'>"
                        f"Score-Zusammensetzung: "
                        f"Nutzung {buch.get('Score_Nutzung', '-')} · "
                        f"Aktualität {buch.get('Score_Aktualitaet', '-')} · "
                        f"Alter {buch.get('Score_Alter', '-')} · "
                        f"Trend {buch.get('Score_Trend', '-')}"
                        f"</span>",
                        unsafe_allow_html=True
                    )
    else:
        st.caption("👉 Klicke auf einen Punkt im Diagramm, um Details anzuzeigen.")

else:
    st.info("Keine ausreichenden Daten für Portfolioanalyse vorhanden.")


# =====================================================
# TABELLE: NUR AUF ABFRUF (EXPANDER UNTEN)
# =====================================================
with st.expander("📋 Liste: Top 50 Bereinigungskandidaten (vollständige Tabelle)"):

    st.caption(
        "Hier finden Sie die 50 Medien mit dem höchsten Bereinigungspotenzial "
        "sortiert nach Score. Für Details klicken Sie bitte auf den Punkt im Diagramm."
    )

    score = df_bestand.sort_values("Bereinigungsscore", ascending=False).head(50)

    spalten = [
        "Medienart",
        "Signatur(1)",
        "Titel",
        "Verfasser I(1)",
        "Kategorie Alter",
        "Aufnahme_Monat_Jahr",
        "Standort(1)",
        "Anzahl_Ausleihen",
        "Ausleihen_pro_Jahr",
        "Ausleihen_365Tage",
        "Umlauf",
        "Umlauf_365Tage",
        "Alter_Jahre",
        "Score_Nutzung",
        "Score_Aktualitaet",
        "Score_Alter",
        "Score_Trend",
        "Bereinigungsscore",
        "Bereinigung"
    ]
    spalten = [c for c in spalten if c in score.columns]

    st.dataframe(score[spalten], hide_index=True, use_container_width=True)

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

if debug_zeiten:
    st.sidebar.caption(f"⏱️ Gesamte Skriptlaufzeit: {time.perf_counter() - _start_zeit:.2f}s")
    with st.sidebar.expander("⏱️ Messverlauf dieser Session"):
        for eintrag in st.session_state.get("bestand_ladezeiten_verlauf", []):
            st.caption(eintrag)