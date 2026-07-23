import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta

def get_sidebar_filters(
    df_users, 
    df_extra=None, 
    prefix="global",
    enable_date_filter=False,
    date_col_name="Ausleihdatum",
    extra_filters_config=None,
    enable_first_loan_toggle=False,
    first_loan_col_name="Erstausleihe",
    extension_count_col="Verlängerung_Anz",
    show_metrics=True
):
    """
    ROBUSTE VERSION mit garantiertem Datum-Filter.
    """
        # NEU: Fehlende Daten robust behandeln
    if df_users is None:
        df_users = pd.DataFrame()

    if df_extra is None:
        df_extra = pd.DataFrame()
    # --- 0. VORBEREITUNG EXTRA DATEN ---
    has_extra = df_extra is not None and not df_extra.empty
    
    # WICHTIG: date_range_val vorab definieren, damit es immer existiert
    date_range_val = None 

    if has_extra and enable_first_loan_toggle:
        if first_loan_col_name not in df_extra.columns:
            if extension_count_col in df_extra.columns:
                def is_first_loan(val):
                    if pd.isna(val): return True
                    if str(val).strip() == "": return True
                    try:
                        if float(val) == 0: return True
                    except ValueError:
                        pass
                    return False
                df_extra[first_loan_col_name] = df_extra[extension_count_col].apply(is_first_loan)
            else:
                if f"{prefix}_warn_shown" not in st.session_state:
                    st.warning(f"Spalte '{extension_count_col}' fehlt. Erstausleihe-Filter inaktiv.")
                    st.session_state[f"{prefix}_warn_shown"] = True
                df_extra[first_loan_col_name] = False
        else:
            def normalize_bool(val):
                if pd.isna(val): return False
                s = str(val).strip().lower()
                return s in ["1", "true", "ja", "yes", "y"]
            df_extra[first_loan_col_name] = df_extra[first_loan_col_name].apply(normalize_bool)

    # --- 1. DATEN VORBEREITEN (Demografie) ---
    group_col = None

    if df_users is not None and not df_users.empty:
        if "Benutzergruppe_Gruppiert" in df_users.columns:
            group_col = "Benutzergruppe_Gruppiert"
        elif "Benutzergruppe" in df_users.columns:
            group_col = "Benutzergruppe"
    gender_col = "Anrede"
    col_door = "Self Service Türöffner"
    col_auth = "Self Service Berechtigung"
    
    if df_users is not None:
        df_for_filter = df_users.copy()
    else:
        df_for_filter = pd.DataFrame()
    
    def clean_gender(val):
        if pd.isna(val): return "Unbekannt"
        val_str = str(val).strip()
        if val_str == "Herr": return "Männlich"
        if val_str == "Frau": return "Weiblich"
        return "Andere"
    
    df_for_filter['Geschlecht_Filter'] = df_for_filter[gender_col].apply(clean_gender) if gender_col in df_for_filter.columns else "Unbekannt"

    min_age, max_age = 0, 100
    if "Geburtsdatum" in df_for_filter.columns:
        df_for_filter['Geburtsdatum_DT'] = pd.to_datetime(df_for_filter['Geburtsdatum'], format='%m/%d/%Y', errors='coerce')
        if df_for_filter['Geburtsdatum_DT'].isna().all():
            df_for_filter['Geburtsdatum_DT'] = pd.to_datetime(df_for_filter['Geburtsdatum'], errors='coerce')
            
        today_dt = pd.Timestamp.now()
        df_for_filter['Alter_Berechnet'] = (today_dt - df_for_filter['Geburtsdatum_DT']).dt.days // 365
        valid_ages = df_for_filter[(df_for_filter['Alter_Berechnet'] >= 0) & (df_for_filter['Alter_Berechnet'] <= 100)]['Alter_Berechnet']
        if not valid_ages.empty:
            min_age, max_age = int(valid_ages.min()), int(valid_ages.max())
    else:
        df_for_filter['Alter_Berechnet'] = np.nan

    def normalize_bool(val):
        if pd.isna(val): return False
        return str(val).strip().lower() in ["1", "true", "ja", "yes", "y"]

    has_door = col_door in df_for_filter.columns
    has_auth = col_auth in df_for_filter.columns
    
    df_for_filter['SS_Tueröffner'] = df_for_filter[col_door].apply(normalize_bool) if has_door else False
    df_for_filter['SS_Berechtigung'] = df_for_filter[col_auth].apply(normalize_bool) if has_auth else False
            
    def get_ss_category(row):
        d, a = row['SS_Tueröffner'], row['SS_Berechtigung']
        if d and a: return "Türöffner & Berechtigung"
        elif d: return "Nur Türöffner"
        elif a: return "Nur Berechtigung"
        else: return "Keine Self-Service"
            
    df_for_filter['SS_Kategorie'] = df_for_filter.apply(get_ss_category, axis=1)

    # --- 2. STATE MANAGEMENT ---
    if group_col:
        unique_groups = sorted(
            df_users[group_col]
            .dropna()
            .astype(str)
            .unique()
        )
    else:
        unique_groups = []
    unique_genders = sorted(df_for_filter['Geschlecht_Filter'].dropna().unique())
    loc_col = 'Ort_Norm' if 'Ort_Norm' in df_for_filter.columns else ('Ort_Validiert' if 'Ort_Validiert' in df_for_filter.columns else 'Wohnort')
    if loc_col in df_for_filter.columns:
        unique_locs = sorted(df_for_filter[loc_col].dropna().unique())
    else:
        unique_locs = []
    
    query_params = st.query_params.to_dict()

    def init_state_safe(key, default_val, url_param=None):
        # ... (bleibt gleich) ...
        if key not in st.session_state:
            if url_param and url_param in query_params:
                val = query_params[url_param]
                if val:
                    st.session_state[key] = val.split(',')
                    return
            st.session_state[key] = default_val

    init_state_safe(f"{prefix}_groups", list(unique_groups), 'groups')
    init_state_safe(f"{prefix}_gender", list(unique_genders), 'gender')
    init_state_safe(f"{prefix}_age", (min_age, max_age))
    
    default_loc = [] if len(unique_locs) > 20 else list(unique_locs)
    init_state_safe(f"{prefix}_location", default_loc, 'location')
    init_state_safe(f"{prefix}_ss_list", [], 'ss')

    extra_filter_keys = {}
    
    # ============================================================
    # FIX HIER: Extra-Filter INITIALISIEREN (UNABHÄNGIG VOM DATUM!)
    # ============================================================
    if has_extra and extra_filters_config:
        for conf in extra_filters_config:
            col = conf['col']
            if col in df_extra.columns:
                # Werte bereinigen und unique machen
                unique_vals = sorted(df_extra[col].dropna().astype(str).unique())

                default_cfg = conf.get("default", list(unique_vals))

                # Falls Default als Index angegeben wurde
                if (
                    isinstance(default_cfg, list)
                    and len(default_cfg) == 1
                    and isinstance(default_cfg[0], int)
                ):
                    idx = default_cfg[0]
                    # leere Werte für die Index-Auswahl ignorieren
                    gültige_werte = [v for v in unique_vals if v.strip() != ""]

                    default_vals = [gültige_werte[idx]] if idx < len(gültige_werte) else []
                else:
                    default_vals = [str(v) for v in default_cfg if str(v) in unique_vals]

                key_ms = f"{prefix}_ms_{col}"
                init_state_safe(key_ms, default_vals, f"ex_{col}")

                extra_filter_keys[col] = key_ms

    # Vorbereitung für Datum
    date_key = f"{prefix}_date_range"
    mode_key = f"{prefix}_period_mode"
    min_d, max_d = None, None
    today = date.today()

    # Datum-Logik bleibt wie vorher, aber OHNE die extra_filters Initialisierung darin
    if has_extra and enable_date_filter and date_col_name in df_extra.columns:
        if not pd.api.types.is_datetime64_any_dtype(df_extra[date_col_name]):
            df_extra[date_col_name] = pd.to_datetime(df_extra[date_col_name], errors='coerce')
        
        min_d = df_extra[date_col_name].min().date()
        max_d = df_extra[date_col_name].max().date()
        
        if pd.isna(min_d) or pd.isna(max_d):
            min_d, max_d = today - timedelta(days=730), today
        else:
            if max_d > today: max_d = today
            if max_d - min_d > timedelta(days=730):
                min_d = max_d - timedelta(days=730)

        if enable_first_loan_toggle:
            init_state_safe(f"{prefix}_first_loan", False, 'first_loan')

    # --- 3. RENDERING ---
    st.sidebar.header("Filter")
    # Defaultwerte, falls keine Nutzerdaten vorhanden sind
    sel_grp = []
    sel_gen = []
    sel_age = (0, 100)
    sel_ss = []
    sel_loc = []
    
    if df_users is not None and not df_users.empty:
        with st.sidebar.expander("👥 Zielgruppe", expanded=False):
            st.subheader("Benutzergruppe")
            c1, c2 = st.columns(2)
            if c1.button("Alle", key=f"{prefix}_btn_all_grp", use_container_width=True):
                st.session_state[f"{prefix}_groups"] = list(unique_groups)
                st.rerun()
            if c2.button("Keine", key=f"{prefix}_btn_none_grp", use_container_width=True):
                st.session_state[f"{prefix}_groups"] = []
                st.rerun()
                
            sel_grp = st.multiselect("Wählen", options=unique_groups, key=f"{prefix}_groups", label_visibility="collapsed", placeholder="Alle")
            st.subheader("Geschlecht")
            sel_gen = st.multiselect("Geschlecht", options=unique_genders, key=f"{prefix}_gender", label_visibility="collapsed", placeholder="Alle")

            st.subheader("Alter")
            if "Geburtsdatum" in df_for_filter.columns:
                sel_age = st.slider("Spanne", min_value=min_age, max_value=max_age, key=f"{prefix}_age")
            else:
                sel_age = (0, 100)
                
            st.subheader("Self-Service")
            current_ss = st.session_state.get(f"{prefix}_ss_list", [])
            
            def update_ss():
                new_ss = []
                if st.session_state.get(f"{prefix}_cb_both"): new_ss.append("Türöffner & Berechtigung")
                if st.session_state.get(f"{prefix}_cb_auth"): new_ss.append("Nur Berechtigung")
                if st.session_state.get(f"{prefix}_cb_door"): new_ss.append("Nur Türöffner")
                st.session_state[f"{prefix}_ss_list"] = new_ss

            c_ss1, c_ss2, c_ss3 = st.columns(3)
            with c_ss1:
                st.checkbox("Beides", value="Türöffner & Berechtigung" in current_ss, key=f"{prefix}_cb_both", on_change=update_ss)
            with c_ss2:
                st.checkbox("Nur App", value="Nur Berechtigung" in current_ss, key=f"{prefix}_cb_auth", on_change=update_ss)
            with c_ss3:
                st.checkbox("Nur Tür", value="Nur Türöffner" in current_ss, key=f"{prefix}_cb_door", on_change=update_ss)
                
            sel_ss = st.session_state[f"{prefix}_ss_list"]
            
            st.subheader("Wohnort")
            if len(unique_locs) > 20: st.caption("💡 Tippen zum Suchen")
            sel_loc = st.multiselect("Orte", options=unique_locs, key=f"{prefix}_location", label_visibility="collapsed", placeholder="Alle")

    # --- DETAILS EXPANDER ---
    if has_extra:
        with st.sidebar.expander("📊 Details (Ausleihe/Medien)", expanded=True):
            
            # Datum Filter Block
            if enable_date_filter and date_col_name in df_extra.columns:
                st.markdown("**📅 Zeitraum-Modus**")
                
                if mode_key not in st.session_state:
                    st.session_state[mode_key] = "Vergleich (24 Monate)"
                
                def on_mode_change():
                    new_mode = st.session_state[mode_key]
                    loc_min = df_extra[date_col_name].min().date()
                    loc_max = df_extra[date_col_name].max().date()
                    if loc_max > today: loc_max = today
                    
                    if new_mode == "Gesamte Daten":
                        new_range = (loc_min, loc_max)
                    else: 
                        suggested_start = date(loc_max.year - 2, 1, 1)
                        if suggested_start < loc_min: suggested_start = loc_min
                        new_range = (suggested_start, loc_max)
                    
                    st.session_state[date_key] = new_range

                period_mode = st.radio(
                    "Ansicht wählen",
                    options=["Gesamte Daten", "Vergleich (24 Monate)"],
                    key=mode_key,
                    horizontal=True,
                    on_change=on_mode_change,
                    help="'Gesamte Daten' zeigt alles. 'Vergleich' setzt auf letzte 24 Monate."
                )
                
                if date_key not in st.session_state:
                    current_mode_init = st.session_state[mode_key]
                    if current_mode_init == "Gesamte Daten":
                        st.session_state[date_key] = (min_d, max_d)
                    else:
                        start_date = max_d - timedelta(days=730)
                        if start_date < min_d: start_date = min_d
                        st.session_state[date_key] = (start_date, max_d)
                
                # Das Widget, das den Wert in date_range_val schreibt
                date_range_val = st.date_input(
                    "Zeitraum (Start - Ende)", 
                    key=date_key, 
                    format="DD.MM.YYYY",
                    help="Wird automatisch angepasst, wenn Sie oben den Modus wechseln."
                )
                
                # Tupel-Sicherheit
                if not isinstance(date_range_val, tuple):
                    prev = st.session_state.get(date_key, (today, today))
                    if isinstance(prev, tuple):
                        date_range_val = (date_range_val, prev[1])
                    else:
                        date_range_val = (date_range_val, date_range_val)
                
                st.divider()

            if enable_first_loan_toggle:
                st.markdown("**⚙️ Optionen**")
                first_loan_only = st.toggle("Nur Erstausleihen", key=f"{prefix}_first_loan")
                st.divider()

            if extra_filters_config:
                for col, key_ms in extra_filter_keys.items():
                    label = next((c['label'] for c in extra_filters_config if c['col'] == col), col)
                    unique_vals = sorted(df_extra[col].dropna().astype(str).unique())
                    st.multiselect(label, options=unique_vals, key=key_ms, placeholder="Alle")
                    st.session_state[f"{prefix}_extra_{col}"] = st.session_state[key_ms]
    
    # Falls has_extra False ist, aber enable_first_loan_toggle trotzdem gesetzt war (Fallback)
    if not has_extra and enable_first_loan_toggle:
         first_loan_only = False

    # --- URL SYNC ---
    def set_param_safe(k, v):
        try:
            if v and str(v).strip() != "" and len(str(v)) < 1500:
                st.query_params[k] = str(v)
            elif k in st.query_params:
                del st.query_params[k]
        except: pass

    groups_str = ",".join(map(str, sel_grp)) if sel_grp else ""
    gender_str = ",".join(map(str, sel_gen)) if sel_gen else ""
    loc_str = ",".join(map(str, sel_loc)) if sel_loc else ""
    ss_str = ",".join(map(str, sel_ss)) if sel_ss else ""
    
    set_param_safe("groups", groups_str)
    set_param_safe("gender", gender_str)
    set_param_safe("age_min", str(sel_age[0]))
    set_param_safe("age_max", str(sel_age[1]))
    set_param_safe("location", loc_str)
    set_param_safe("ss", ss_str)
    
    # Datum Sync nur wenn val definiert ist
    if date_range_val and isinstance(date_range_val, tuple):
        set_param_safe("date_start", str(date_range_val[0]))
        set_param_safe("date_end", str(date_range_val[1]))
    
    if has_extra and enable_first_loan_toggle:
        # Variable first_loan_only könnte hier fehlen wenn nicht im Expander definiert
        # Wir holen sie sicherheitshalber aus dem State
        fl_val = st.session_state.get(f"{prefix}_first_loan", False)
        set_param_safe("first_loan", "1" if fl_val else "")

    if extra_filters_config:
        for col in extra_filter_keys.keys():
            vals = st.session_state.get(f"{prefix}_extra_{col}", [])
            val_str = ",".join(map(str, vals)) if vals else ""
            set_param_safe(f"ex_{col}", val_str)

    # --- 4. FILTER ANWENDEN ---
    df_res = df_for_filter.copy()
    if sel_grp and group_col:
        df_res = df_res[df_res[group_col].isin(sel_grp)]
    if sel_gen: df_res = df_res[df_res['Geschlecht_Filter'].isin(sel_gen)]
    if "Geburtsdatum" in df_res.columns:
        df_res = df_res[(df_res['Alter_Berechnet'] >= sel_age[0]) & (df_res['Alter_Berechnet'] <= sel_age[1])]
    if sel_ss: df_res = df_res[df_res['SS_Kategorie'].isin(sel_ss)]
    if sel_loc and loc_col in df_res.columns:
        df_res = df_res[df_res[loc_col].isin(sel_loc)]
    
    df_extra_res = None
    if has_extra:
        df_extra_res = df_extra.copy()
        # Filter anwenden nur wenn date_range_val ein Tupel ist
        if enable_date_filter and date_range_val and isinstance(date_range_val, tuple) and date_col_name in df_extra_res.columns:
            mask = (df_extra_res[date_col_name].dt.date >= date_range_val[0]) & \
                   (df_extra_res[date_col_name].dt.date <= date_range_val[1])
            df_extra_res = df_extra_res[mask]
        
        if extra_filters_config:
            for col in extra_filter_keys.keys():
                vals = st.session_state.get(f"{prefix}_extra_{col}", [])
                if vals:
                    df_extra_res = df_extra_res[df_extra_res[col].astype(str).isin(vals)]
        
        if enable_first_loan_toggle:
            fl_val = st.session_state.get(f"{prefix}_first_loan", False)
            if fl_val and first_loan_col_name in df_extra_res.columns:
                df_extra_res = df_extra_res[df_extra_res[first_loan_col_name] == True]

        id_col_users = 'Nummer' 
        id_col_extra = 'Ausleihperson' 
        if id_col_users in df_res.columns and id_col_extra in df_extra_res.columns:
            df_res[id_col_users] = df_res[id_col_users].astype(str)
            df_extra_res[id_col_extra] = df_extra_res[id_col_extra].astype(str)
            df_extra_res = df_extra_res.merge(df_res[[id_col_users]], left_on=id_col_extra, right_on=id_col_users, how='inner')

    st.sidebar.divider()
    if show_metrics:
        text = f"{len(df_res):,}"

        if df_extra_res is not None:
            text += f" / {len(df_extra_res):,} Transaktionen"

        st.sidebar.caption(
            f"📊 Ergebnisse: {len(df_res):,}"
            + (
                f" / {len(df_extra_res):,} Transaktionen"
                if df_extra_res is not None else ""
            )
        )

    # Sicherstellen, dass period_mode im Return ist, auch wenn has_extra False (unwahrscheinlich)
    p_mode = st.session_state.get(mode_key, "Gesamte Daten") if has_extra else "Gesamte Daten"

    return df_res, df_extra_res, {
        "groups": sel_grp, 
        "gender": sel_gen, 
        "age_range": sel_age, 
        "locations": sel_loc, 
        "ss_filter": sel_ss,
        "date_range": date_range_val, # Immer zurückgeben (kann None sein wenn kein extra)
        "first_loan_only": st.session_state.get(f"{prefix}_first_loan", False) if has_extra else False,
        "period_mode": p_mode,
        "group_col": group_col,
        "gender_col": "Geschlecht_Filter",
        "age_col": "Alter_Berechnet",
        "location_col": loc_col
    }