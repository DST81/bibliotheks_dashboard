import streamlit as st
import pandas as pd
import textwrap
from pathlib import Path
import base64
import html
from src.theme import (
    PRIMARY,
    MUTED,
    BORDER,
    CARD_BG,
    SURFACE_MUTED,
    COLOR_PLACEHOLDER_BG,
    COLOR_PLACEHOLDER_TEXT,
    COLOR_NEUTRAL,
)

def _html_value(value):
    return html.escape("" if value is None else str(value))

def kpi_box(title, current, previous=None, previous_label="Vorjahr gesamt", suffix="", subtext=None, color=PRIMARY):
    if isinstance(previous, (int, float)):
        previous_text = f"{previous_label}: {previous:,}".replace(",", "'")
    elif previous is not None:
        previous_text = f"{previous_label}: {previous}"
    else:
        previous_text = None

    if isinstance(current, int):
        current_text = f"{current:,}".replace(",", "'")
    elif isinstance(current, float):
        current_text = f"{current:,.1f}".replace(",", "'")
    else:
        current_text = str(current)
    if suffix:
        current_text += f" {suffix}"

    info = []

    if previous_text:
        info.append(previous_text)

    if subtext:
        info.append(subtext)

    previous_block = ""
    info_text = "<br>".join(_html_value(item) for item in info) if info else "&nbsp;"
    safe_title = _html_value(title)
    safe_current_text = _html_value(current_text)

    previous_block = (
        f'<div style="'
        f'font-size:13px;'
        f'color:{MUTED};'
        f'margin-top:8px;'
        f'line-height:1.4;'
        f'min-height:20px;'
        f'">'
        f'{info_text}'
        f'</div>'
    )
   
    html=(
        f'<div style="border:1px solid {BORDER};border-radius:12px;padding:15px;'
        f'background:{CARD_BG};box-shadow:0 2px 6px rgba(0,0,0,0.05);'
        f'min-height:130px;box-sizing:border-box;">'
        f'<div style="font-size:14px;color:{MUTED};min-height:42px;line-height:1.4;">{safe_title}</div>'
        f'<div style="font-size:32px;font-weight:700;color:{color};">{safe_current_text}</div>'
        f'{previous_block}'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

def show_media_detail(buch, farben):
    if buch is None:
        st.info("👉 Wählen Sie zuerst ein Medium aus.")
        return
    bewertung = buch.get("Bereinigung", None)
    badge_farbe = farben.get(bewertung, COLOR_NEUTRAL)

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
                    f"background:{COLOR_PLACEHOLDER_BG};border-radius:8px;"
                    "display:flex;align-items:center;justify-content:center;"
                    f"color:{COLOR_PLACEHOLDER_TEXT};font-size:0.85em;text-align:center;'>"
                    "📕<br>Kein Cover</div>",
                    unsafe_allow_html=True
                )
            # NR Zugang unterhalb des Covers
            nr_zugang = buch.get("NR Zugang", "-")
            nr_zugang_html = _html_value(nr_zugang)

            st.markdown(
                f"""
                <div style="
                    width:170px;
                    text-align:center;
                    margin-top:6px;
                    font-size:0.8rem;
                    color:{MUTED};
                ">
                    Zugangsnummer: <strong>{nr_zugang_html}</strong>
                </div>
                """,
                unsafe_allow_html=True
            )

        with col_info:
            st.markdown(f"#### {_html_value(buch.get('Titel', '-'))}")
            autor = buch.get("Verfasser I(1)", "")
            if autor and str(autor).strip():
                st.markdown(f"<span style='color:{MUTED};'>{_html_value(autor)}</span>", unsafe_allow_html=True)

            st.markdown(
                f"<span style='background-color:{badge_farbe}22; "
                f"color:{badge_farbe}; padding:4px 12px; border-radius:14px; "
                f"font-size:0.85em; font-weight:600;'>{_html_value(bewertung)}</span>"
                f"&nbsp;&nbsp;"
                f"<span style='color:{MUTED}; font-size:0.85em;'>"
                f"📍 {_html_value(buch.get('Standort(1)', '-'))} &nbsp;·&nbsp; "
                f"📚 {_html_value(buch.get('Medienart', '-'))} &nbsp; &nbsp; "
                f"📅 {_html_value(buch.get('Aufnahme_Monat_Jahr', '-'))} &nbsp; &nbsp; "
                f"👶 {_html_value(buch.get('Kategorie Alter', '-'))}"
                f"</span>",
                unsafe_allow_html=True
            )

            # --- Reihenkontext ---
            reihe = buch.get("Reihe(1)", "")
            reihen_hinweis = buch.get("Reihen_Hinweis", "")

            if reihe and str(reihe).strip() and reihen_hinweis:
                band = buch.get("Band", "-")
                anzahl_baende= buch.get("Reihen_Anzahl_Bande", None)
                median_info = ""
                if pd.notna(anzahl_baende):
                    median_info = f" . {int(anzahl_baende)} Bände im Bestand"

                reihen_hinweis_html = _html_value(reihen_hinweis).replace(". ", ".<br>")
                st.markdown(
                    f"<div style='margin-top:8px; padding:8px 12px; "
                    f"background:{SURFACE_MUTED}; border-radius:8px; font-size:0.85em;'>"
                    f"📚 <strong>Reihe:</strong> {_html_value(reihe)} (Band {_html_value(band)}){_html_value(median_info)}<br>"
                    f"{reihen_hinweis_html}"
                    f"</div>",
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
                f"<span style='color:{MUTED}; font-size:0.8em;'>"
                f"Score-Zusammensetzung: "
                f"Nutzung {_html_value(buch.get('Score_Nutzung', '-'))} · "
                f"Aktualität {_html_value(buch.get('Score_Aktualitaet', '-'))} · "
                f"Alter {_html_value(buch.get('Score_Alter', '-'))} · "
                f"Trend {_html_value(buch.get('Score_Trend', '-'))}"
                f"</span>",
                unsafe_allow_html=True
            )
def show_new_acquisition_detail(buch):
    if buch is None:
        st.info("👉 Wählen Sie zuerst ein Medium aus.")
        return

    st.divider()

    with st.container(border=True):

        col_bild, col_info = st.columns([1, 2.6], gap="medium")

        # =========================
        # COVER
        # =========================
        with col_bild:
            cover_url = buch.get("URL_Cover", "")

            if cover_url and str(cover_url).strip():
                st.image(str(cover_url), width=170)
            else:
                st.markdown(
                    "<div style='width:170px;height:230px;"
                    f"background:{COLOR_PLACEHOLDER_BG};border-radius:8px;"
                    "display:flex;align-items:center;justify-content:center;"
                    f"color:{COLOR_PLACEHOLDER_TEXT};font-size:0.85em;text-align:center;'>"
                    "📕<br>Kein Cover</div>",
                    unsafe_allow_html=True
                )

        # =========================
        # INFORMATIONEN
        # =========================
        with col_info:

            st.markdown(
                f"#### {_html_value(buch.get('Titel', '-'))}"
            )

            autor = buch.get("Verfasser I(1)", "")

            if autor and str(autor).strip():
                st.markdown(
                    f"<span style='color:{MUTED};'>{_html_value(autor)}</span>",
                    unsafe_allow_html=True
                )

            # Reihe
            reihe = buch.get("Reihe(1)", "")
            band = buch.get("Band", "")

            if (
                pd.notna(reihe)
                and str(reihe).strip()
            ):
                reihe_text = str(reihe).strip()

                if pd.notna(band) and str(band).strip():
                    reihe_text += f" · Band {band}"

                st.markdown(
                    f"<span style='color:{MUTED};'>"
                    f"📚 {_html_value(reihe_text)}"
                    f"</span>",
                    unsafe_allow_html=True
                )

            st.write("")

            # =========================
            # METADATEN
            # =========================

            lieferant = buch.get("Lieferant", "-")
            preis = buch.get("Preis", None)
            aufnahme = buch.get("Datum der Aufnahme", None)
            nr_zugang = buch.get("NR Zugang", "-")

            if pd.notna(preis):
                preis_text = f"CHF {float(preis):.2f}"
            else:
                preis_text = "-"

            if pd.notna(aufnahme):
                try:
                    aufnahme_text = pd.Timestamp(
                        aufnahme
                    ).strftime("%d.%m.%Y")
                except:
                    aufnahme_text = str(aufnahme)
            else:
                aufnahme_text = "-"

            st.markdown(
                f"<span style='color:{MUTED}; font-size:0.85em;'>"
                f"📦 <strong>Lieferant:</strong> {_html_value(lieferant)}"
                f"&nbsp;&nbsp;·&nbsp;&nbsp;"
                f"💰 <strong>Preis:</strong> {_html_value(preis_text)}"
                f"&nbsp;&nbsp;·&nbsp;&nbsp;"
                f"📅 <strong>Aufnahme:</strong> {_html_value(aufnahme_text)}"
                f"</span>",
                unsafe_allow_html=True
            )

            st.write("")

            # =========================
            # KENNZAHLEN
            # =========================

            m1, m2, m3, m4 = st.columns(4)

            with m1:
                st.metric(
                    "Preis",
                    preis_text
                )

            with m2:
                st.metric(
                    "Ausleihen",
                    f"{int(buch.get('Ausleihen', 0))}"
                )

            with m3:
                st.metric(
                    "Ausleihen / Preis",
                    (
                        f"{float(buch.get('Ausleihen', 0)) / float(preis):.2f}"
                        if pd.notna(preis) and float(preis) > 0
                        else "-"
                    )
                )

            with m4:
                st.metric(
                    "NR Zugang",
                    str(nr_zugang)
                )

            st.caption(
                "Die Ausleihzahl bezieht sich auf den aktuell "
                "gefilterten Zeitraum."
            )
def title_with_icon(
    title,
    icon,
    icon_size=52,
    gap=10,
    level="title",
):
    styles = {
        "title": {
            "font_size": "2.75rem",
            "font_weight": "700",
            "line_height": "1.15",
            "margin_bottom": "0.5rem",
        },
        "header": {
            "font_size": "2rem",
            "font_weight": "700",
            "line_height": "1.2",
            "margin_bottom": "0.45rem",
        },
        "subheader": {
            "font_size": "1.55rem",
            "font_weight": "600",
            "line_height": "1.25",
            "margin_bottom": "0.35rem",
        },
    }
    style = styles.get(level, styles["title"])

    svg = Path(icon).read_text(encoding="utf-8")
    svg_b64 = base64.b64encode(
        svg.encode("utf-8")
    ).decode("utf-8")

    safe_title = html.escape(title)

    st.html(
        f"""
        <div style="
            display:flex;
            align-items:center;
            gap:{gap}px;
            margin:0 0 {style["margin_bottom"]} 0;
        ">
            <img
                src="data:image/svg+xml;base64,{svg_b64}"
                style="
                    width:{icon_size}px;
                    height:{icon_size}px;
                    object-fit:contain;
                    flex-shrink:0;
                "
            />

            <div style="
                font-size:{style["font_size"]};
                font-weight:{style["font_weight"]};
                line-height:{style["line_height"]};
                margin:0;
                padding:0;
            ">
                {safe_title}
            </div>
        </div>
        """
    )
