import streamlit as st
import pandas as pd
import textwrap

def kpi_box(title, current, previous=None, previous_label="Vorjahr gesamt", suffix="", subtext=None, color="#264653"):
    if isinstance(previous, (int, float)):
        previous_text = f"{previous_label}: {previous:,}".replace(",", "'")
    elif previous is not None:
        previous_text = str(previous)
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
    if info:
        previous_block = (
            '<div style="font-size:13px;color:#666;margin-top:8px;line-height:1.4;">'
            + "<br>".join(info)
            + "</div>"
        )
   
    html=(
        '<div style="border:1px solid #E6E6E6;border-radius:12px;padding:15px;'
        'background:white;box-shadow:0 2px 6px rgba(0,0,0,0.05);">'
        f'<div style="font-size:14px;color:#666;">{title}</div>'
        f'<div style="font-size:32px;font-weight:700;color:{color};">{current_text}</div>'
        f'{previous_block}'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

def show_media_detail(buch, farben):
    if buch is None:
        st.info("👉 Wählen Sie zuerst ein Medium aus.")
        return
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

            # --- Reihenkontext ---
            reihe = buch.get("Reihe(1)", "")
            reihen_hinweis = buch.get("Reihen_Hinweis", "")

            if reihe and str(reihe).strip() and reihen_hinweis:
                band = buch.get("Band", "-")
                anzahl_baende= buch.get("Reihen_Anzahl_Bande", None)
                median_info = ""
                if pd.notna(anzahl_baende):
                    median_info = f" . {int(anzahl_baende)} Bände im Bestand"

                reihen_hinweis_html = reihen_hinweis.replace(". ", ".<br>")
                st.markdown(
                    f"<div style='margin-top:8px; padding:8px 12px; "
                    f"background:#f7f7f7; border-radius:8px; font-size:0.85em;'>"
                    f"📚 <strong>Reihe:</strong> {reihe} (Band {band}){median_info}<br>"
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
                f"<span style='color:#888; font-size:0.8em;'>"
                f"Score-Zusammensetzung: "
                f"Nutzung {buch.get('Score_Nutzung', '-')} · "
                f"Aktualität {buch.get('Score_Aktualitaet', '-')} · "
                f"Alter {buch.get('Score_Alter', '-')} · "
                f"Trend {buch.get('Score_Trend', '-')}"
                f"</span>",
                unsafe_allow_html=True
            )
