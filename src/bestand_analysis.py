import streamlit as st
import pandas as pd
import numpy as np
import re


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

# Funktion zur Analyse von Reihen
def parse_band(wert, max_band=50):
    """
    Versucht eine plausible Bandnummer zu extrahieren.
    Gibt None zurück, wenn der wert nicht als sinnvolle Bandnummer gilt
    (z.B, Signaturen, Inventarnummern oder Tippfehler in diesem Feld).
    """
    s = str(wert).strip()
    hauptteil = s.split("/")[0].strip()  # bei "3/1" nur den Hauptband nehmen

    try:
        f = float(hauptteil)
    except (ValueError, TypeError):
        return None

    if not f.is_integer():
        # z.B. 2.1 - keine gültige ganzzahlige Bandnummer
        return None

    n = int(f)
    if n <= 0 or n > max_band:
        return None
    return n

def normalisiere_reihe(name):
    if pd.isna(name):
        return None

    s=str(name).strip().lower()

    # führende Artikel entfernen
    s = re.sub(r"^(der|die|das|ein|eine)\s+", "",s)

    # Mehrfach-Leerzeichen entfernen
    s = re.sub(r"\s"," ",s)
    return s

def berechne_reihenkonsistenz(df_bestand: pd.DataFrame) -> pd.DataFrame:
    """
    Ergänzt df_bestand um Reihenkontext-Spalten:
    - Reihen_Anzahl_Baende: Wie viele Bände der Reihe im Bestand
    - Reihen_Median_Score: Median-Bereinigungsscore der übrigen Bände
    - Reihen_Luecken: fehlende Bandnummern innerhalb der Reihe
    - Reihen_Hinweis: kurzer Text für Tabelle/Detailansicht
    """
    df = df_bestand.copy()
    SCHWELLE_GUTE_REIHE= df['Bereinigungsscore'].quantile(0.33)
    SCHWELLE_SCHLECHTE_REIHE= df['Bereinigungsscore'].quantile(0.66)
    ABWEICHUNGS_SCORE = 0.5 *df['Bereinigungsscore'].std()
    


    df['Reihen_Anzahl_Baende'] = pd.NA
    df['Reihen_Median_Score'] = pd.NA
    df['Reihen_Luecken'] = pd.NA
    df['Reihen_Hinweis'] = pd.NA

    if "Reihe(1)" not in df.columns or "Band" not in df.columns:
        return df

    hat_Reihe = df["Reihe(1)"].notna() & (df["Reihe(1)"].astype(str).str.strip() != "")

    gruppen = df[hat_Reihe].copy()
    gruppen["Reihe_norm"] = gruppen["Reihe(1)"].apply(normalisiere_reihe)

    for reihe, gruppe in gruppen.groupby("Reihe_norm"):
        idx = gruppe.index
        anzahl = len(gruppe)

        df.loc[idx, "Reihen_Anzahl_Baende"] = anzahl
        median_score = gruppe['Bereinigungsscore'].median()
        df.loc[idx, "Reihen_Median_Score"] = median_score

        MAX_BAND = 50 # Realistische Obergrenze
        baende_geparst = gruppe['Band'].apply(lambda w: parse_band(w,MAX_BAND))
        baende_numerisch = baende_geparst.dropna()



        luecken_text = ""
        if len(baende_numerisch) >= 2:
            vorhanden = sorted(int(b) for b in baende_numerisch.unique())
            bereich = range(1, vorhanden[-1]+1)
            luecken = [b for b in bereich if b not in vorhanden]
            gesamt_baende = len(bereich)
            vorhanden_baende = len(vorhanden)

            if luecken:
                luecken_text = ", ".join(str(l) for l in luecken)
                df.loc[idx, "Reihen_Luecken"] = luecken_text

        for i in idx:
            eigener_score = df.at[i, "Bereinigungsscore"]
            diff = eigener_score - median_score

            if anzahl < 2:
                hinweis = ""

            elif luecken_text:
                band_text = "Band" if len(luecken)==1 else "Bände"
                hinweis = (
                    f"⚠️ Reihe unvollständig. "
                    f"{vorhanden_baende} von {gesamt_baende} Bänden vorhanden "
                    f"(fehlend: {band_text} {luecken_text})"
                    )

            elif median_score >= SCHWELLE_SCHLECHTE_REIHE:
                if diff < -ABWEICHUNGS_SCORE:
                    hinweis = (
                        f"⚠️ Gesamte Reihe wird wenig genutzt "
                        f"(Median {median_score:.0f}), "
                        f"dieses Band jedoch etwas häufiger."
                    )
                else:
                    hinweis = (
                        f"🗑️ Gesamte Reihe wird wenig genutzt "
                        f"(Median {median_score:.0f})."
                    )
            elif median_score <= SCHWELLE_GUTE_REIHE:
                if diff > ABWEICHUNGS_SCORE:
                    hinweis = (
                        f"⚠️ Dieses Band wird deutlich weniger genutzt "
                        f"als die übrige Reihe "
                        f"(Median {median_score:.0f})."
                    )
                elif diff < -ABWEICHUNGS_SCORE:
                    hinweis = (
                        f"⭐ Dieses Band wird deutlich häufiger genutzt "
                        f"als die übrige Reihe "
                        f"(Median {median_score:.0f})."
                    )
                else:
                    hinweis = (
                        f"✅ Gesamte Reihe wird gut genutzt "
                        f"(Median {median_score:.0f})."
                    )

            else:
                if abs(diff) > ABWEICHUNGS_SCORE:
                    hinweis = (
                        f"ℹ️ Nutzung dieses Bandes weicht deutlich "
                        f"vom Rest der Reihe ab "
                        f"(Median {median_score:.0f})."
                    )
                else:
                    hinweis = (
                        f"ℹ️ Reihe wird durchschnittlich genutzt "
                        f"(Median {median_score:.0f})."
                    )

            df.at[i, "Reihen_Hinweis"] = hinweis

    return df
@st.cache_data(show_spinner="Reihenkonsistenz und Scores werden analysiert...", hash_funcs={pd.DataFrame: id})
def berechne_bestand_mit_reihen(df_books:pd.DataFrame, df_loans:pd.DataFrame) -> pd.DataFrame:
    df= berechne_bestand_scores(df_books,df_loans)
    df =berechne_reihenkonsistenz(df)
    return df