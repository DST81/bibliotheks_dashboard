import json
from pathlib import Path
from components.icons import EINSTELLUNGEN
from components.ui import title_with_icon
from src.theme import COLOR_HOLIDAY

import streamlit as st


st.set_page_config(page_title="Einstellungen", page_icon="assets/einstellungen.svg", layout="wide")
title_with_icon("Einstellungen", EINSTELLUNGEN)

col1,col2 = st.columns([7,1])
with col1:
    
    st.caption("Ferien und Saisonzeiten für Auswertungen mit Kalenderwochen pflegen.")

CONFIG_FILE = Path("data/config.json")


def load_config():
    if not CONFIG_FILE.exists():
        return {"ferien": []}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        st.error(f"Fehler beim Lesen der Config: {e}")
        return {"ferien": []}

    return {
        "ferien": config.get("ferien", []),
        "openlibrary": config.get("openlibrary", {}),
    }


def save_config(config):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


config = load_config()
ferien = config.setdefault("ferien", [])
openlibrary = config.setdefault("openlibrary", {})
openlibrary.setdefault("start_stunde", 6)
openlibrary.setdefault("end_stunde", 23)
with col2:
    if st.button("Einstellungen speichern", type="primary"):
        save_config(config)
        st.success("Einstellungen gespeichert.")

with st.expander("OpenLibrary-Öffnungszeiten"):
    title,ol_col1, ol_col2 = st.columns([2,1,1])
    with title:
        #st.subheader("OpenLibrary-Öffnungszeiten")
        st.caption("Diese Stunden werden für die OpenLibrary-Auswertungen nach Stunde verwendet.")


    with ol_col1:
        openlibrary["start_stunde"] = st.number_input(
            "Startstunde",
            min_value=0,
            max_value=23,
            value=int(openlibrary.get("start_stunde", 6)),
            step=1,
        )


    with ol_col2:
        openlibrary["end_stunde"] = st.number_input(
            "Endstunde",
            min_value=int(openlibrary["start_stunde"]),
            max_value=23,
            value=max(
                int(openlibrary.get("end_stunde", 23)),
                int(openlibrary["start_stunde"]),
            ),
            step=1,
        )
        st.caption(
            f"Angezeigt werden Zeitfenster von {int(openlibrary['start_stunde']):02d}:00 "
            f"bis {int(openlibrary['end_stunde']) + 1:02d}:00."
        )
with st.expander("Ferien / Saisonzeiten"):
    st.markdown("### Neue Ferien hinzufügen")

    c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 1])

    with c1:
        neuer_name = st.text_input("Name")

    with c2:
        neuer_start = st.number_input("Start-KW", 1, 53, 1)

    with c3:
        neues_ende = st.number_input("End-KW", 1, 53, 1)

    with c4:
        neue_farbe = st.color_picker("Farbe", COLOR_HOLIDAY)

    with c5:
        if st.button("➕ Ferien hinzufügen"):
            if neuer_name.strip():
                ferien.append({
                    "name": neuer_name.strip(),
                    "start_kw": int(neuer_start),
                    "end_kw": int(neues_ende),
                    "farbe": neue_farbe,
                    "aktiv": True,
                })
                save_config(config)
                st.success("Ferien gespeichert.")
                st.rerun()
            else:
                st.error("Bitte eine Bezeichnung eingeben.")

    st.subheader("Ferien / Saisonzeiten")
    st.caption(
        "Diese Zeiträume können in Diagrammen als farbige Bereiche angezeigt werden."
    )

    delete_index = None

    for i, eintrag in enumerate(ferien):
        c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 1, 1, 0.5, 0.5])

        with c1:
            ferien[i]["name"] = st.text_input(
                "Bezeichnung",
                value=eintrag.get("name", ""),
                key=f"name_{i}",
            )

        with c2:
            ferien[i]["start_kw"] = st.number_input(
                "Start-KW",
                1,
                53,
                value=int(eintrag.get("start_kw", 1)),
                key=f"start_{i}",
            )

        with c3:
            ferien[i]["end_kw"] = st.number_input(
                "End-KW",
                1,
                53,
                value=int(eintrag.get("end_kw", 1)),
                key=f"ende_{i}",
            )

        with c4:
            ferien[i]["farbe"] = st.color_picker(
                "Farbe",
                value=eintrag.get("farbe", COLOR_HOLIDAY),
                key=f"farbe_{i}",
            )

        with c5:
            ferien[i]["aktiv"] = st.checkbox(
                "Aktiv",
                value=eintrag.get("aktiv", True),
                key=f"aktiv_{i}",
            )

        with c6:
            st.write("")
            st.write("")
            if st.button("🗑", key=f"del_{i}"):
                delete_index = i

    if delete_index is not None:
        ferien.pop(delete_index)
        save_config(config)
        st.rerun()

   


with st.expander("Vorschau der config.json"):
    st.json(config)
