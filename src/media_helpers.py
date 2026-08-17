import altair as alt


def sortierter_balken(df, x_col, y_col, x_label, y_label, color="#4C78A8", height=380):
    """Balkendiagramm mit absteigend nach Wert sortierter x-Achse."""
    return (
        alt.Chart(df)
        .mark_bar(color=color)
        .encode(
            x=alt.X(f"{x_col}:N", title=x_label, sort="-y"),
            y=alt.Y(f"{y_col}:Q", title=y_label),
            tooltip=[
                alt.Tooltip(f"{x_col}:N", title=x_label),
                alt.Tooltip(f"{y_col}:Q", title=y_label, format=",.2f"),
            ],
        )
        .properties(height=height)
    )


def kategorie_bereinigen(df, spalte):
    """Fehlende oder leere Werte einer Kategorie-Spalte vereinheitlichen."""
    df[spalte] = df[spalte].fillna("Unbekannt").astype(str).str.strip()
    df.loc[df[spalte] == "", spalte] = "Unbekannt"
    return df
