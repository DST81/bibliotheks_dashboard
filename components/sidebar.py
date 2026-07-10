import streamlit as st
from datetime import date
from dateutil.relativedelta import relativedelta
import pandas as pd

def init_session_state():
    if "filters" not in st.session_state:
        st.session_state.filters = {}

def render_sidebar(df, config):
    init_session_state()
    st.sidebar.header("Globale Filter")

    # Sicherstellen, dass config ein Dictionary ist
    if not isinstance(config, dict):
        st.sidebar.error("Config ist ungültig.")
        config = {}

    filters_config = config.get("filters", {})
    
    # Fallback: Wenn 'visible' nicht definiert ist, nimm alle Spalten oder eine sinnvolle Teilmenge
    # Dein Code nimmt hier alle DF Spalten, was bei vielen Spalten unübersichtlich wird.
    # Oft ist es besser, hier eine explizite Liste zu erwarten oder nur bekannte Spalten zu nehmen.
    visible_filters = filters_config.get("visible", df.columns.tolist())
    
    defaults = filters_config.get("defaults", {})

    # --- Toggle: Nur Erstausleihen ---
    # Prüfen ob der Key im DF existiert, falls dies eine Spalte filtern soll, 
    # oder wenn es nur ein globaler Schalter ist.
    nur_erstausleihen = st.sidebar.toggle(
        "Nur Erstausleihen",
        value=defaults.get("Nur Erstausleihen", False)
    )
    st.session_state.filters["nur_erstausleihen"] = nur_erstausleihen

    # --- Datum ---
    date_range = None
    if "Ausleihdatum" in df.columns:
        # Sicherstellen, dass das Datum datetime ist für min/max Berechnung
        # Falls df["Ausleihdatum"] noch Strings enthält, hier pd.to_datetime() nutzen
        min_date_val = df["Ausleihdatum"].min()
        max_date_val = df["Ausleihdatum"].max()

        if pd.notna(min_date_val) and pd.notna(max_date_val):
            # Umwandlung in date Objekte falls notwendig
            min_date = min_date_val.date() if hasattr(min_date_val, 'date') else min_date_val
            max_date = max_date_val.date() if hasattr(max_date_val, 'date') else max_date_val

            years_back = defaults.get("date_years_back", 2)
            today = date.today()

            default_start = max(
                today - relativedelta(years=years_back),
                min_date
            )

            date_range = st.sidebar.date_input(
                "Ausleihdatum",
                value=(default_start, max_date)
            )
    
    st.session_state.filters["date_range"] = date_range

    # --- Multiselect Helper ---
    def multiselect(label, column):
        # Prüfen ob Spalte sichtbar sein soll UND im DataFrame existiert
        if column not in visible_filters or column not in df.columns:
            return []

        # Unique Werte bereinigen
        raw_values = df[column].dropna().unique()
        values = sorted(str(v) for v in raw_values if str(v).strip())

        # Defaults holen
        default_vals = defaults.get(column, values)
        
        # Sicherstellen, dass Defaults existieren und gültig sind
        if not default_vals:
            default_vals = values
        else:
            # Filtern, nur Werte nehmen, die auch wirklich in den Daten vorkommen
            default_vals = [v for v in default_vals if v in values]

        selected = st.sidebar.multiselect(
            label,
            options=values,
            default=default_vals
        )

        st.session_state.filters[column] = selected
        return selected

    # Aufrufe für die spezifischen Spalten
    # Hinweis: "Zweigstelle" ist NICHT in deiner config.json unter "visible" aufgeführt.
    # Daher wird dieser Filter mit deinem aktuellen Setup NICHT angezeigt, 
    # es sei denn, "visible" fehlt ganz oder du fügst "Zweigstelle" zur Liste hinzu.
    sel_zweig = multiselect("Zweigstelle", "Zweigstelle")
    sel_medien = multiselect("Medienart", "Medienart")
    # Nutze die neue Spalte, falls sie existiert:
    group_column = "Benutzergruppe_Gruppiert" if "Benutzergruppe_Gruppiert" in df.columns else "Benutzergruppe"
    label = "Benutzergruppe (gruppiert)" if group_column == "Benutzergruppe_Gruppiert" else "Benutzergruppe"

    sel_gruppe = multiselect(label, group_column)
    sel_alter = multiselect("Kategorie Alter", "Kategorie Alter")

    return {
        "date_range": date_range,
        "nur_erstausleihen": nur_erstausleihen,
        "Zweigstelle": sel_zweig,
        "Medienart": sel_medien,
        "Benutzergruppe": sel_gruppe,
        "Kategorie Alter": sel_alter
    }
