from datetime import date

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta


def init_session_state():
    if "filters" not in st.session_state:
        st.session_state.filters = {}


def render_sidebar(df, config=None):
    init_session_state()
    st.sidebar.header("Globale Filter")

    nur_erstausleihen = st.sidebar.toggle(
        "Nur Erstausleihen",
        value=False,
    )
    st.session_state.filters["nur_erstausleihen"] = nur_erstausleihen

    date_range = None
    if "Ausleihdatum" in df.columns:
        min_date_val = df["Ausleihdatum"].min()
        max_date_val = df["Ausleihdatum"].max()

        if pd.notna(min_date_val) and pd.notna(max_date_val):
            min_date = min_date_val.date() if hasattr(min_date_val, "date") else min_date_val
            max_date = max_date_val.date() if hasattr(max_date_val, "date") else max_date_val
            default_start = max(date.today() - relativedelta(years=2), min_date)

            date_range = st.sidebar.date_input(
                "Ausleihdatum",
                value=(default_start, max_date),
            )

    st.session_state.filters["date_range"] = date_range

    def multiselect(label, column):
        if column not in df.columns:
            return []

        values = sorted(
            str(v)
            for v in df[column].dropna().unique()
            if str(v).strip()
        )

        selected = st.sidebar.multiselect(
            label,
            options=values,
            default=values,
        )

        st.session_state.filters[column] = selected
        return selected

    sel_zweig = multiselect("Zweigstelle", "Zweigstelle")
    sel_medien = multiselect("Medienart", "Medienart")
    sel_gruppe = multiselect("Benutzergruppe", "Benutzergruppe")
    sel_alter = multiselect("Kategorie Alter", "Kategorie Alter")

    return {
        "date_range": date_range,
        "nur_erstausleihen": nur_erstausleihen,
        "Zweigstelle": sel_zweig,
        "Medienart": sel_medien,
        "Benutzergruppe": sel_gruppe,
        "Kategorie Alter": sel_alter,
    }
