from __future__ import annotations

from typing import Any

import pandas as pd


def format_filter_value(value: Any, *, currency: bool = False) -> str:
    if value in (None, "", []):
        return "Alle"

    if isinstance(value, tuple) and len(value) == 2:
        left, right = value
        if currency and isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return f"CHF {left:,.0f} - {right:,.0f}".replace(",", "'")
        if hasattr(left, "strftime") and hasattr(right, "strftime"):
            return f"{left:%d.%m.%Y} - {right:%d.%m.%Y}"
        return f"{left} - {right}"

    if isinstance(value, list):
        if len(value) <= 3:
            return ", ".join(map(str, value))
        return f"{len(value)} ausgewählt"

    return str(value)


def build_home_filter_summary(filter_state: dict) -> list[tuple[str, str]]:
    extra_filters = filter_state.get("extra_filters", {})

    return [
        ("Ausleihzeitraum", format_filter_value(filter_state.get("date_range"))),
        ("Benutzergruppen", format_filter_value(filter_state.get("groups"))),
        ("Geschlecht", format_filter_value(filter_state.get("gender"))),
        ("Alter", format_filter_value(filter_state.get("age_range"))),
        ("Wohnort", format_filter_value(filter_state.get("locations"))),
        ("Zweigstelle", format_filter_value(extra_filters.get("Zweigstelle"))),
        ("Medienart", format_filter_value(extra_filters.get("Medienart"))),
        ("Lesealter", format_filter_value(extra_filters.get("Kategorie Alter"))),
        ("Erstausleihen", "Ja" if filter_state.get("first_loan_only") else "Nein"),
    ]


def build_media_filter_summary(filter_state: dict) -> list[tuple[str, str]]:
    catalog_filters = filter_state.get("catalog_filters", {})
    extra_filters = filter_state.get("extra_filters", {})

    return [
        ("Ausleihzeitraum", format_filter_value(filter_state.get("date_range"))),
        ("Neuanschaffung", format_filter_value(catalog_filters.get("Datum der Aufnahme"))),
        ("Preis", format_filter_value(catalog_filters.get("Preis"), currency=True)),
        ("Zweigstelle", format_filter_value(extra_filters.get("Zweigstelle"))),
        ("Lieferant", format_filter_value(catalog_filters.get("Lieferant"))),
        ("Medienart", format_filter_value(catalog_filters.get("Medienart"))),
        ("Lesealter", format_filter_value(catalog_filters.get("Kategorie Alter"))),
        ("Standort", format_filter_value(catalog_filters.get("Standort(1)"))),
        ("Sprache", format_filter_value(catalog_filters.get("Sprache(1)"))),
        ("Erstausleihen", "Ja" if filter_state.get("first_loan_only") else "Nein"),
    ]


def apply_non_date_catalog_filters(df: pd.DataFrame, catalog_filters: dict) -> pd.DataFrame:
    filtered = df.copy()

    for col, value in catalog_filters.items():
        if col == "Datum der Aufnahme" or col not in filtered.columns:
            continue

        if isinstance(value, list) and value:
            filtered = filtered[filtered[col].astype(str).isin([str(v) for v in value])]

        elif isinstance(value, tuple) and len(value) == 2:
            numeric = pd.to_numeric(filtered[col], errors="coerce")
            if numeric.notna().any():
                filtered = filtered[numeric.between(value[0], value[1])]

    return filtered


def apply_loan_context_filters(
    df_loans: pd.DataFrame,
    df_users_filtered: pd.DataFrame,
    filter_state: dict,
    year: int | None = None,
) -> pd.DataFrame:
    loans = df_loans.copy()

    if "Nummer" in df_users_filtered.columns and "Ausleihperson" in loans.columns:
        user_ids = df_users_filtered["Nummer"].dropna().astype(str).unique()
        loans["Ausleihperson"] = loans["Ausleihperson"].astype(str)
        loans = loans[loans["Ausleihperson"].isin(user_ids)]

    for col, values in filter_state.get("extra_filters", {}).items():
        if values and col in loans.columns:
            loans = loans[loans[col].astype(str).isin([str(v) for v in values])]

    if filter_state.get("first_loan_only", False) and "Erstausleihe" in loans.columns:
        loans = loans[loans["Erstausleihe"]]

    if year is not None and "Ausleihdatum" in loans.columns:
        loan_dates = pd.to_datetime(loans["Ausleihdatum"], errors="coerce")
        loans = loans[loan_dates.dt.year == year]

    return loans


def build_yearly_media_kpis(
    df_catalog_base: pd.DataFrame,
    df_loans_base: pd.DataFrame,
    df_users_filtered: pd.DataFrame,
    filter_state: dict,
    year: int,
) -> dict[str, float | int]:
    catalog_filters = filter_state.get("catalog_filters", {})
    catalog = apply_non_date_catalog_filters(df_catalog_base, catalog_filters)

    catalog["Preis"] = pd.to_numeric(catalog["Preis"], errors="coerce")
    catalog["Datum der Aufnahme"] = pd.to_datetime(catalog["Datum der Aufnahme"], errors="coerce")
    catalog_year = catalog[catalog["Datum der Aufnahme"].dt.year == year].copy()

    loans_year = apply_loan_context_filters(df_loans_base, df_users_filtered, filter_state, year=year)

    if "NR Zugang" in catalog_year.columns and "NR Zugang" in loans_year.columns:
        media_ids = catalog_year["NR Zugang"].dropna().astype(str).unique()
        loans_year = loans_year[loans_year["NR Zugang"].astype(str).isin(media_ids)]

    media_count = len(catalog_year)
    loan_count = len(loans_year)

    return {
        "media_count": media_count,
        "total_cost": catalog_year["Preis"].sum(),
        "avg_price": catalog_year["Preis"].mean() if catalog_year["Preis"].notna().any() else 0,
        "loan_count": loan_count,
        "avg_loans": loan_count / media_count if media_count > 0 else 0,
    }


def percent_change(current: float | int, previous: float | int | None) -> float | None:
    if previous in (None, 0):
        return None
    return (current - previous) / previous * 100


def format_delta(current: float | int, previous: float | int | None, decimals: int = 1) -> str | None:
    change = percent_change(current, previous)
    if change is None:
        return None

    symbol = "🟢" if change >= 0 else "🔴"
    return f"{symbol} {change:+.{decimals}f} %"


def delta_color(current: float | int, previous: float | int | None) -> str:
    change = percent_change(current, previous)
    if change is None or change >= 0:
        return "#2E7D32"
    return "#C62828"


def format_pdf_delta(current: float | int, previous: float | int | None) -> str:
    change = percent_change(current, previous)
    if change is None:
        return "Veränderung n/a"
    return f"Veränderung {change:+.1f} %"
