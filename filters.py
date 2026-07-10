import streamlit as st
import pandas as pd
import numpy as np

def get_sidebar_filters(df_users, prefix="global"):
    """
    Optimierte Sidebar-Filter inkl. erweiterter Self-Service Filter (Türöffner & Berechtigung).
    """
    
    # --- 1. VORBEREITUNG DER DATEN ---
    group_col = "Benutzergruppe_Gruppiert" if "Benutzergruppe_Gruppiert" in df_users.columns else "Benutzergruppe"
    gender_col = "Anrede"
    
    # Spaltennamen definieren
    col_door = "Self Service Türöffner"
    col_auth = "Self Service Berechtigung"
    
    df_for_filter = df_users.copy()
    
    # Geschlecht bereinigen
    def clean_gender(val):
        if pd.isna(val): return "Unbekannt"
        val_str = str(val).strip()
        if val_str == "Herr": return "Männlich"
        if val_str == "Frau": return "Weiblich"
        return "Andere"
    
    if gender_col in df_for_filter.columns:
        df_for_filter['Geschlecht_Filter'] = df_for_filter[gender_col].apply(clean_gender)
    else:
        df_for_filter['Geschlecht_Filter'] = "Unbekannt"

    # Alter berechnen
    min_age, max_age = 0, 100
    if "Geburtsdatum" in df_for_filter.columns:
        df_for_filter['Geburtsdatum_DT'] = pd.to_datetime(df_for_filter['Geburtsdatum'], format='%m/%d/%Y', errors='coerce')
        today = pd.Timestamp.now()
        df_for_filter['Alter_Berechnet'] = (today - df_for_filter['Geburtsdatum_DT']).dt.days // 365
        valid_ages = df_for_filter[(df_for_filter['Alter_Berechnet'] >= 0) & (df_for_filter['Alter_Berechnet'] <= 100)]['Alter_Berechnet']
        if not valid_ages.empty:
            min_age = int(valid_ages.min())
            max_age = int(valid_ages.max())
    else:
        df_for_filter['Alter_Berechnet'] = np.nan

    # --- SELF SERVICE LOGIK ---
    # Wir prüfen, welche der beiden Spalten existieren und normalisieren die Werte (1, true, ja -> True)
    def normalize_bool(val):
        if pd.isna(val): return False
        s = str(val).strip().lower()
        return s in ["1", "true", "ja", "yes", "y"]

    has_door = col_door in df_for_filter.columns
    has_auth = col_auth in df_for_filter.columns
    
    if has_door:
        df_for_filter['SS_Tueröffner'] = df_for_filter[col_door].apply(normalize_bool)
    else:
        df_for_filter['SS_Tueröffner'] = False
        
    if has_auth:
        df_for_filter['SS_Berechtigung'] = df_for_filter[col_auth].apply(normalize_bool)
    else:
        df_for_filter['SS_Berechtigung'] = False

    # Kombinierte Kategorie für den Filter erstellen
    def get_ss_category(row):
        door = row['SS_Tueröffner']
        auth = row['SS_Berechtigung']
        
        if door and auth:
            return "Türöffner & Berechtigung"
        elif door:
            return "Nur Türöffner"
        elif auth:
            return "Nur Berechtigung"
        else:
            return "Keine Self-Service"
            
    df_for_filter['SS_Kategorie'] = df_for_filter.apply(get_ss_category, axis=1)
    
    # Verfügbare Kategorien für den Filter (nur die, die auch in Daten vorkommen, ausser "Keine" wenn wir filtern wollen)
    # Wir bieten im Filter explizit die aktiven Optionen an
    ss_options = []
    if has_door or has_auth:
        ss_options = ["Türöffner & Berechtigung", "Nur Türöffner", "Nur Berechtigung"]
        # "Keine Self-Service" lassen wir als Option weg, wenn man spezifisch filtern will, 
        # aber der User kann "Alle" wählen (leere Auswahl im Multiselect).

    # --- 2. STATE & URL MANAGEMENT ---
    key_groups = f"{prefix}_groups"
    key_gender = f"{prefix}_gender"
    key_age = f"{prefix}_age"
    key_location = f"{prefix}_location"
    key_ss = f"{prefix}_ss" # Neuer Key für Self-Service
    
    query_params = st.query_params.to_dict()
    
    # Optionen ermitteln
    unique_groups = sorted(df_for_filter[group_col].dropna().unique())
    unique_genders = sorted(df_for_filter['Geschlecht_Filter'].dropna().unique())
    
    loc_col = 'Ort_Norm' if 'Ort_Norm' in df_for_filter.columns else ('Ort_Validiert' if 'Ort_Validiert' in df_for_filter.columns else 'Wohnort')
    unique_locs = sorted(df_for_filter[loc_col].dropna().unique())
    
    # --- INITIALISIERUNG ---
    
    # Gruppen
    if key_groups not in st.session_state:
        st.session_state[key_groups] = query_params['groups'].split(',') if 'groups' in query_params else unique_groups
        
    # Geschlecht
    if key_gender not in st.session_state:
        st.session_state[key_gender] = [g for g in (query_params['gender'].split(',') if 'gender' in query_params else unique_genders) if g in unique_genders]

    # Alter
    if key_age not in st.session_state:
        if 'age_min' in query_params and 'age_max' in query_params:
            st.session_state[key_age] = (int(query_params['age_min']), int(query_params['age_max']))
        else:
            st.session_state[key_age] = (min_age, max_age)
            
    # Wohnort
    if key_location not in st.session_state:
        st.session_state[key_location] = query_params['location'].split(',') if 'location' in query_params else ([] if len(unique_locs) > 20 else unique_locs)

    # Self-Service (Default: Alle anzeigen)
    if key_ss not in st.session_state:
        if 'ss' in query_params:
            st.session_state[key_ss] = query_params['ss'].split(',')
        else:
            st.session_state[key_ss] = [] # Leer = Alle anzeigen

    # --- 3. SIDEBAR RENDERING ---
    
    st.sidebar.header("Filter")
    st.sidebar.caption("Zielgruppe eingrenzen")

    # --- A) BENUTZERGRUPPE ---
    st.sidebar.subheader("Benutzergruppe")
    col_btn1, col_btn2 = st.sidebar.columns(2)
    with col_btn1:
        if st.button("Alle", key=f"{prefix}_btn_all_grp", use_container_width=True):
            st.session_state[key_groups] = unique_groups
            st.rerun()
    with col_btn2:
        if st.button("Keine", key=f"{prefix}_btn_none_grp", use_container_width=True):
            st.session_state[key_groups] = []
            st.rerun()
            
    selected_groups = st.sidebar.multiselect(
        "Wählen",
        options=unique_groups,
        key=key_groups,
        label_visibility="collapsed",
        placeholder=f"{len(st.session_state[key_groups])} gewählt" if st.session_state[key_groups] else "Alle"
    )

    # --- B) GESCHLECHT ---
    st.sidebar.subheader("Geschlecht")
    selected_gender = st.sidebar.multiselect(
        "Geschlecht",
        options=unique_genders,
        key=key_gender,
        label_visibility="collapsed",
        placeholder="Alle"
    )

    # --- C) ALTER ---
    st.sidebar.subheader("Alter")
    if "Geburtsdatum" in df_for_filter.columns and not df_for_filter['Alter_Berechnet'].isna().all():
        selected_age = st.sidebar.slider(
            "Spanne",
            min_value=min_age,
            max_value=max_age,
            value=st.session_state[key_age],
            key=key_age,
            step=1
        )
    else:
        selected_age = (0, 100)

# --- D) SELF-SERVICE (Checkboxen nebeneinander & umgekehrte Reihenfolge) ---
    selected_ss = [] # Default: Keine Auswahl = Alle anzeigen
    
    if has_door or has_auth:
        st.sidebar.subheader("Self-Service")
        st.sidebar.caption("Welche Berechtigungen sollen angezeigt werden?")
        
        # Wir erstellen 3 Spalten nebeneinander
        # Da es nur 3 Optionen sind, passen sie gut in eine Reihe
        col_ss1, col_ss2, col_ss3 = st.sidebar.columns(3)
        
        # Reihenfolge: 1. Beides, 2. Nur Türöffner, 3. Nur Berechtigung
        # (Von "Vollzugriff" zu "Teilzugriff")
        
        with col_ss1:
            if st.checkbox("App & Tür", value=False, key=f"{prefix}_cb_both", help="Türöffner & Berechtigung"):
                selected_ss.append("Türöffner & Berechtigung")
        
        with col_ss2:
            if st.checkbox("Nur App", value=False, key=f"{prefix}_cb_auth", help="Selbstverbuchung, aber kein Zutritt"):
                selected_ss.append("Nur Berechtigung")
                
        with col_ss3:
            if st.checkbox("Nur Tür", value=False, key=f"{prefix}_cb_door", help="Türöffner, aber keine Selbstverbuchung"):
                selected_ss.append("Nur Türöffner")
        
        # Hinweis, wenn nichts ausgewählt ist
        if not selected_ss:
            st.sidebar.info("Keine Auswahl: Alle Nutzenden werden angezeigt.", icon="ℹ️")
            
        # URL Sync
        if selected_ss:
            st.query_params["ss"] = ",".join(selected_ss)
        elif "ss" in st.query_params:
            del st.query_params["ss"]
            
    else:
        selected_ss = []

    # --- E) WOHNORT ---
    st.sidebar.subheader("Wohnort")
    if len(unique_locs) > 20:
        st.sidebar.caption("💡 Tippen zum Suchen")
    
    selected_locs = st.sidebar.multiselect(
        "Orte",
        options=unique_locs,
        key=key_location,
        label_visibility="collapsed",
        placeholder="Alle Orte" if not st.session_state[key_location] else f"{len(st.session_state[key_location])} gewählt"
    )

    # --- 4. URL SYNC ---
    def set_param(key, val):
        if val: st.query_params[key] = val
        elif key in st.query_params: del st.query_params[key]

    set_param("groups", ",".join(selected_groups) if selected_groups else "")
    set_param("gender", ",".join(selected_gender) if selected_gender else "")
    set_param("age_min", str(selected_age[0]))
    set_param("age_max", str(selected_age[1]))
    set_param("ss", ",".join(selected_ss) if selected_ss else "")
    set_param("location", ",".join(selected_locs) if selected_locs else "")

    # --- 5. FILTER ANWENDEN ---
    df_filtered = df_for_filter.copy()
    
    if selected_groups:
        df_filtered = df_filtered[df_filtered[group_col].isin(selected_groups)]
        
    if selected_gender:
        df_filtered = df_filtered[df_filtered['Geschlecht_Filter'].isin(selected_gender)]
        
    if "Geburtsdatum" in df_filtered.columns:
        df_filtered = df_filtered[
            (df_filtered['Alter_Berechnet'] >= selected_age[0]) & 
            (df_filtered['Alter_Berechnet'] <= selected_age[1])
        ]
        
    # Self-Service Filter Logik
    if selected_ss:
        # Wir filtern rows, deren 'SS_Kategorie' in der Auswahl ist
        df_filtered = df_filtered[df_filtered['SS_Kategorie'].isin(selected_ss)]
        # Hinweis: "Keine Self-Service" Nutzer werden hier automatisch ausgeblendet, wenn eine Auswahl getroffen wird.
        
    if selected_locs:
        df_filtered = df_filtered[df_filtered[loc_col].isin(selected_locs)]
        
    # --- 6. METRIK ---
    st.sidebar.divider()
    st.sidebar.metric("Ergebnisse", f"{len(df_filtered):,}")
    
    return df_filtered, {
        "groups": selected_groups,
        "gender": selected_gender,
        "age_range": selected_age,
        "locations": selected_locs,
        "ss_filter": selected_ss,
        "group_col": group_col,
        "gender_col": "Geschlecht_Filter",
        "age_col": "Alter_Berechnet",
        "location_col": loc_col
    }