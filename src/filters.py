import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta
from src.utils import normalize_media_id


# ============================================================
# Hilfsfunktionen
# ============================================================

def _init_state_safe(key, default_value, query_params=None, url_param=None):
    """Initialisiert einen Session-State-Wert, falls er noch nicht existiert."""
    if key in st.session_state:
        return

    if query_params is not None and url_param and url_param in query_params:
        value = query_params[url_param]

        if isinstance(value, list):
            value = value[0] if value else ""

        if value not in (None, ""):
            if isinstance(default_value, tuple):
                try:
                    parts = str(value).split(",")
                    if len(parts) == 2:
                        st.session_state[key] = tuple(
                            pd.to_datetime(p).date() for p in parts
                        )
                        return
                except Exception:
                    pass

            if isinstance(default_value, list):
                st.session_state[key] = str(value).split(",")
                return

            try:
                if isinstance(default_value, bool):
                    st.session_state[key] = str(value).lower() in (
                        "1", "true", "ja", "yes", "y"
                    )
                    return
                if isinstance(default_value, int):
                    st.session_state[key] = int(value)
                    return
                if isinstance(default_value, float):
                    st.session_state[key] = float(value)
                    return
            except (ValueError, TypeError):
                pass

    st.session_state[key] = default_value


def _normalize_bool(value):
    if pd.isna(value):
        return False
    return str(value).strip().lower() in (
        "1", "true", "ja", "yes", "y"
    )


def _clean_gender(value):
    if pd.isna(value):
        return "Unbekannt"

    value = str(value).strip()

    if value == "Herr":
        return "Männlich"
    if value == "Frau":
        return "Weiblich"

    return "Andere"


def _render_catalog_filter(df_catalog, conf, key_prefix):
    """
    Rendert einen Katalogfilter abhängig vom konfigurierten Typ.

    Unterstützte Typen:
    - multiselect
    - range
    - date_preset
    """
    col = conf["col"]
    label = conf.get("label", col)
    filter_type = conf.get("type", "multiselect")
    key = f"{key_prefix}_catalog_{col}"

    if col not in df_catalog.columns:
        return None

    # --------------------------------------------------------
    # Mehrfachauswahl
    # --------------------------------------------------------
    if filter_type == "multiselect":
        values = (
            df_catalog[col]
            .dropna()
            .astype(str)
            .str.strip()
        )
        values = values[values != ""].unique().tolist()

        # Häufigste Werte zuerst
        values = (
            df_catalog.loc[
                df_catalog[col].notna(),
                col
            ]
            .astype(str)
            .str.strip()
            .loc[lambda s: s != ""]
            .value_counts()
            .index
            .tolist()
        )

        default_values = conf.get("default", [])
        default_values = [
            str(v) for v in default_values
            if str(v) in values
        ]

        _init_state_safe(key, default_values)

        st.multiselect(
            label,
            options=values,
            key=key,
            placeholder="Alle",
            help=(
                "Tippen, um einen Wert zu suchen."
                if len(values) > 15 else None
            ),
        )

        return st.session_state.get(key, [])

    # --------------------------------------------------------
    # Zahlenbereich / Slider
    # --------------------------------------------------------
    if filter_type == "range":
        numeric = pd.to_numeric(df_catalog[col], errors="coerce").dropna()

        if numeric.empty:
            st.caption(f"Keine gültigen Werte für «{label}».")
            st.session_state[key] = None
            return None

        minimum = float(numeric.min())
        maximum = float(numeric.max())

        if minimum == maximum:
            st.caption(f"{label}: {minimum:g}")
            st.session_state[key] = (minimum, maximum)
            return minimum, maximum

        step = conf.get("step", 1.0)

        # Für Preise standardmässig 5 CHF-Schritte
        if conf.get("currency", False):
            step = conf.get("step", 5.0)

        _init_state_safe(key, (minimum, maximum))

        # Session-State kann nach Datenänderungen ausserhalb des gültigen
        # Bereichs liegen. Deshalb vor dem Widget sicher begrenzen.
        current = st.session_state.get(key, (minimum, maximum))

        try:
            current = (
                max(minimum, min(float(current[0]), maximum)),
                max(minimum, min(float(current[1]), maximum)),
            )
            if current[0] > current[1]:
                current = (minimum, maximum)
        except (TypeError, ValueError, IndexError):
            current = (minimum, maximum)

        st.session_state[key] = current

        return st.slider(
            label,
            min_value=minimum,
            max_value=maximum,
            value=current,
            step=step,
            key=key,
            format="%.0f CHF" if conf.get("currency", False) else None,
        )

    # --------------------------------------------------------
    # Aufnahmedatum / Zeit-Presets
    # --------------------------------------------------------
    if filter_type == "date_preset":
        options = conf.get(
            "options",
            [
                "Alle Medien",
                "Aktuelles Jahr",
                "Letzte 365 Tage",
                "Letzte 2 Jahre",
            ],
        )

        default = conf.get("default", "Alle Medien")
        _init_state_safe(key, default)

        return st.selectbox(
            label,
            options=options,
            key=key,
        )

    st.warning(
        f"Unbekannter Katalogfilter-Typ '{filter_type}' für '{col}'."
    )
    return None


# ============================================================
# SIDEBAR-FILTER
# ============================================================

def get_sidebar_filters(
    df_users,
    df_extra=None,
    df_catalog=None,
    prefix="global",
    enable_date_filter=False,
    date_col_name="Ausleihdatum",
    extra_filters_config=None,
    enable_first_loan_toggle=False,
    first_loan_col_name="Erstausleihe",
    extension_count_col="Verlängerung_Anz",
    show_metrics=True,
    catalog_filters_config=None,
    expander_defaults=None,
    expander_labels=None,
):
    """
    Zentrale Filterfunktion für Benutzer, Ausleihen und Katalog.

    extra_filters_config:
        Filter auf df_extra, z.B.
        [
            {"col": "Zweigstelle", "label": "Zweigstelle"},
            {"col": "Medienart", "label": "Medienart"},
        ]

    catalog_filters_config:
        Filter auf df_catalog, z.B.
        [
            {"col": "Lieferant", "label": "Lieferant", "type": "multiselect"},
            {"col": "Preis", "label": "Preis (CHF)", "type": "range",
             "currency": True, "step": 5.0},
            {"col": "Datum der Aufnahme", "label": "Neuanschaffung",
             "type": "date_preset"},
        ]
    """

    if df_users is None:
        df_users = pd.DataFrame()

    if df_extra is None:
        df_extra = pd.DataFrame()

    if df_catalog is None:
        df_catalog = pd.DataFrame()

    has_extra = not df_extra.empty
    has_catalog = not df_catalog.empty
    expander_defaults = expander_defaults or {}
    expander_labels = expander_labels or {}

    query_params = st.query_params.to_dict()

    # --------------------------------------------------------
    # 0. Erstausleihe vorbereiten
    # --------------------------------------------------------

    if has_extra and enable_first_loan_toggle:
        if first_loan_col_name not in df_extra.columns:
            if extension_count_col in df_extra.columns:

                def is_first_loan(value):
                    if pd.isna(value):
                        return True

                    if str(value).strip() == "":
                        return True

                    try:
                        return float(value) == 0
                    except (ValueError, TypeError):
                        return False

                df_extra = df_extra.copy()
                df_extra[first_loan_col_name] = (
                    df_extra[extension_count_col]
                    .apply(is_first_loan)
                )

            else:
                warn_key = f"{prefix}_warn_shown"

                if warn_key not in st.session_state:
                    st.warning(
                        f"Spalte '{extension_count_col}' fehlt. "
                        "Erstausleihe-Filter inaktiv."
                    )
                    st.session_state[warn_key] = True

                df_extra = df_extra.copy()
                df_extra[first_loan_col_name] = False

        else:
            df_extra = df_extra.copy()
            df_extra[first_loan_col_name] = (
                df_extra[first_loan_col_name]
                .apply(_normalize_bool)
            )

    # --------------------------------------------------------
    # 1. Benutzerdaten vorbereiten
    # --------------------------------------------------------

    if not df_users.empty:
        if "Benutzergruppe" in df_users.columns:
            group_col = "Benutzergruppe"
        else:
            group_col = None
    else:
        group_col = None

    df_for_filter = df_users.copy()

    if "Anrede" in df_for_filter.columns:
        df_for_filter["Geschlecht_Filter"] = (
            df_for_filter["Anrede"].apply(_clean_gender)
        )
    else:
        df_for_filter["Geschlecht_Filter"] = "Unbekannt"

    # --------------------------------------------------------
    # Alter berechnen
    # --------------------------------------------------------

    min_age = 0
    max_age = 100

    if "Geburtsdatum" in df_for_filter.columns:
        geburtsdatum = pd.to_datetime(
            df_for_filter["Geburtsdatum"],
            format="%m/%d/%Y",
            errors="coerce",
        )

        if geburtsdatum.isna().all():
            geburtsdatum = pd.to_datetime(
                df_for_filter["Geburtsdatum"],
                errors="coerce",
            )

        df_for_filter["Geburtsdatum_DT"] = geburtsdatum

        today_dt = pd.Timestamp.now()

        df_for_filter["Alter_Berechnet"] = (
            (today_dt - df_for_filter["Geburtsdatum_DT"]).dt.days
            // 365
        )

        valid_ages = df_for_filter.loc[
            df_for_filter["Alter_Berechnet"].between(0, 100),
            "Alter_Berechnet",
        ].dropna()

        if not valid_ages.empty:
            min_age = int(valid_ages.min())
            max_age = int(valid_ages.max())
    else:
        df_for_filter["Alter_Berechnet"] = np.nan

    # --------------------------------------------------------
    # Self-Service
    # --------------------------------------------------------

    col_door = "Self Service Türöffner"
    col_auth = "Self Service Berechtigung"

    has_door = col_door in df_for_filter.columns
    has_auth = col_auth in df_for_filter.columns

    df_for_filter["SS_Tueröffner"] = (
        df_for_filter[col_door].apply(_normalize_bool)
        if has_door else False
    )

    df_for_filter["SS_Berechtigung"] = (
        df_for_filter[col_auth].apply(_normalize_bool)
        if has_auth else False
    )

    def get_ss_category(row):
        door = row["SS_Tueröffner"]
        auth = row["SS_Berechtigung"]

        if door and auth:
            return "Türöffner & Berechtigung"
        if door:
            return "Nur Türöffner"
        if auth:
            return "Nur Berechtigung"
        return "Keine Self-Service"

    df_for_filter["SS_Kategorie"] = (
        df_for_filter.apply(get_ss_category, axis=1)
    )

    # --------------------------------------------------------
    # Verfügbare Benutzerfilter
    # --------------------------------------------------------

    if group_col:
        unique_groups = sorted(
            df_users[group_col]
            .dropna()
            .astype(str)
            .unique()
        )
    else:
        unique_groups = []

    unique_genders = sorted(
        df_for_filter["Geschlecht_Filter"]
        .dropna()
        .astype(str)
        .unique()
    )

    if "Ort_Norm" in df_for_filter.columns:
        loc_col = "Ort_Norm"
    elif "Ort_Validiert" in df_for_filter.columns:
        loc_col = "Ort_Validiert"
    elif "Wohnort" in df_for_filter.columns:
        loc_col = "Wohnort"
    else:
        loc_col = None

    if loc_col:
        unique_locs = sorted(
            df_for_filter[loc_col]
            .dropna()
            .astype(str)
            .unique()
        )
    else:
        unique_locs = []

    # --------------------------------------------------------
    # Session State
    # --------------------------------------------------------

    _init_state_safe(
        f"{prefix}_groups",
        list(unique_groups),
        query_params,
        "groups",
    )

    _init_state_safe(
        f"{prefix}_gender",
        list(unique_genders),
        query_params,
        "gender",
    )

    _init_state_safe(
        f"{prefix}_age",
        (min_age, max_age),
    )

    default_loc = (
        []
        if len(unique_locs) > 20
        else list(unique_locs)
    )

    _init_state_safe(
        f"{prefix}_location",
        default_loc,
        query_params,
        "location",
    )

    _init_state_safe(
        f"{prefix}_ss_list",
        [],
        query_params,
        "ss",
    )

    # --------------------------------------------------------
    # Ausleihfilter initialisieren
    # --------------------------------------------------------

    extra_filter_keys = {}

    if has_extra and extra_filters_config:
        for conf in extra_filters_config:
            col = conf["col"]

            if col not in df_extra.columns:
                continue

            values = (
                df_extra[col]
                .dropna()
                .astype(str)
                .str.strip()
            )
            values = values[values != ""].unique().tolist()

            default_cfg = conf.get("default", [])

            if (
                isinstance(default_cfg, list)
                and len(default_cfg) == 1
                and isinstance(default_cfg[0], int)
            ):
                idx = default_cfg[0]
                valid_values = [v for v in values if v.strip()]

                default_values = (
                    [valid_values[idx]]
                    if idx < len(valid_values)
                    else []
                )
            else:
                default_values = [
                    str(v)
                    for v in default_cfg
                    if str(v) in values
                ]

            key = f"{prefix}_extra_{col}"

            _init_state_safe(
                key,
                default_values,
                query_params,
                f"ex_{col}",
            )

            extra_filter_keys[col] = key

    # --------------------------------------------------------
    # Datum Ausleihe vorbereiten
    # --------------------------------------------------------

    date_key = f"{prefix}_date_range"
    valid_date_key = f"{prefix}_date_range_valid"
    mode_key = f"{prefix}_period_mode"
    all_data_label = "Alle verfügbaren Ausleihen"
    recent_year_label = "Letzte 12 Monate"

    date_range_val = None
    min_d = None
    max_d = None
    today = date.today()

    if (
        has_extra
        and enable_date_filter
        and date_col_name in df_extra.columns
    ):
        df_extra[date_col_name] = pd.to_datetime(
            df_extra[date_col_name],
            errors="coerce",
        )

        valid_dates = df_extra[date_col_name].dropna()

        if valid_dates.empty:
            min_d = today - timedelta(days=730)
            max_d = today
        else:
            min_d = valid_dates.min().date()
            max_d = valid_dates.max().date()

            if max_d > today:
                max_d = today

            if max_d - min_d > timedelta(days=730):
                min_d = max_d - timedelta(days=730)

        if mode_key not in st.session_state:
            st.session_state[mode_key] = recent_year_label

        if st.session_state[mode_key] == "Gesamte Daten":
            st.session_state[mode_key] = all_data_label
        elif st.session_state[mode_key] == "Vergleich (12 Monate)":
            st.session_state[mode_key] = recent_year_label

        def on_mode_change():
            new_mode = st.session_state[mode_key]

            if new_mode == all_data_label:
                new_range = (min_d, max_d)
            else:
                start_date = max_d - timedelta(days=365)
                if start_date < min_d:
                    start_date = min_d

                new_range = (start_date, max_d)

            st.session_state[date_key] = new_range
            st.session_state[valid_date_key] = new_range

        if date_key not in st.session_state:
            if st.session_state[mode_key] == all_data_label:
                st.session_state[date_key] = (min_d, max_d)
            else:
                start_date = max_d - timedelta(days=365)
                if start_date < min_d:
                    start_date = min_d

                st.session_state[date_key] = (start_date, max_d)

        if valid_date_key not in st.session_state:
            st.session_state[valid_date_key] = st.session_state[date_key]

        _init_state_safe(
            f"{prefix}_first_loan",
            True,
            query_params,
            "first_loan",
        )

    # --------------------------------------------------------
    # 2. RENDERING
    # --------------------------------------------------------

    st.sidebar.header("Filter")

    sel_grp = []
    sel_gen = []
    sel_age = (min_age, max_age)
    sel_ss = []
    sel_loc = []

    # --------------------------------------------------------
    # Zielgruppe
    # --------------------------------------------------------

    if not df_users.empty:
        with st.sidebar.expander(
            expander_labels.get("target", "👥 Zielgruppe"),
            expanded=expander_defaults.get("target", False),
        ):

            st.subheader("Benutzergruppe")

            c1, c2 = st.columns(2)

            if c1.button(
                "Alle",
                key=f"{prefix}_btn_all_grp",
                use_container_width=True,
            ):
                st.session_state[f"{prefix}_groups"] = list(unique_groups)
                st.rerun()

            if c2.button(
                "Keine",
                key=f"{prefix}_btn_none_grp",
                use_container_width=True,
            ):
                st.session_state[f"{prefix}_groups"] = []
                st.rerun()

            sel_grp = st.multiselect(
                "Wählen",
                options=unique_groups,
                key=f"{prefix}_groups",
                label_visibility="collapsed",
                placeholder="Alle",
            )

            st.subheader("Geschlecht")

            sel_gen = st.multiselect(
                "Geschlecht",
                options=unique_genders,
                key=f"{prefix}_gender",
                label_visibility="collapsed",
                placeholder="Alle",
            )

            st.subheader("Alter")

            if "Geburtsdatum" in df_for_filter.columns:
                sel_age = st.slider(
                    "Spanne",
                    min_value=min_age,
                    max_value=max_age,
                    key=f"{prefix}_age",
                )

            st.subheader("Self-Service")

            current_ss = st.session_state.get(
                f"{prefix}_ss_list",
                [],
            )

            def update_ss():
                new_ss = []

                if st.session_state.get(
                    f"{prefix}_cb_both",
                    False,
                ):
                    new_ss.append("Türöffner & Berechtigung")

                if st.session_state.get(
                    f"{prefix}_cb_auth",
                    False,
                ):
                    new_ss.append("Nur Berechtigung")

                if st.session_state.get(
                    f"{prefix}_cb_door",
                    False,
                ):
                    new_ss.append("Nur Türöffner")

                st.session_state[f"{prefix}_ss_list"] = new_ss

            c_ss1, c_ss2, c_ss3 = st.columns(3)

            with c_ss1:
                st.checkbox(
                    "Beides",
                    value="Türöffner & Berechtigung" in current_ss,
                    key=f"{prefix}_cb_both",
                    on_change=update_ss,
                )

            with c_ss2:
                st.checkbox(
                    "Nur App",
                    value="Nur Berechtigung" in current_ss,
                    key=f"{prefix}_cb_auth",
                    on_change=update_ss,
                )

            with c_ss3:
                st.checkbox(
                    "Nur Tür",
                    value="Nur Türöffner" in current_ss,
                    key=f"{prefix}_cb_door",
                    on_change=update_ss,
                )

            sel_ss = st.session_state.get(
                f"{prefix}_ss_list",
                [],
            )

            st.subheader("Wohnort")

            if len(unique_locs) > 20:
                st.caption("💡 Tippen zum Suchen")

            sel_loc = st.multiselect(
                "Orte",
                options=unique_locs,
                key=f"{prefix}_location",
                label_visibility="collapsed",
                placeholder="Alle",
            )

    # --------------------------------------------------------
    # Ausleihe
    # --------------------------------------------------------

    if has_extra:
        with st.sidebar.expander(
            expander_labels.get("loans", "📊 Ausleihe"),
            expanded=expander_defaults.get("loans", True),
        ):

            if (
                enable_date_filter
                and date_col_name in df_extra.columns
                and min_d is not None
            ):
                st.markdown("**📅 Zeitraum**")

                st.radio(
                    "Zeitraum-Vorauswahl",
                    options=[
                        recent_year_label,
                        all_data_label,
                    ],
                    key=mode_key,
                    horizontal=True,
                    on_change=on_mode_change,
                    label_visibility="collapsed",
                )

                date_range_val = st.date_input(
                    "Zeitraum",
                    key=date_key,
                    format="DD.MM.YYYY",
                )

                if (
                    isinstance(date_range_val, tuple)
                    and len(date_range_val) == 2
                ):
                    st.session_state[valid_date_key] = date_range_val
                else:
                    date_range_val = st.session_state.get(
                        valid_date_key,
                        (min_d, max_d),
                    )
                    st.info(
                        "Bitte ein Start- und Enddatum wählen. "
                        "Bis dahin bleibt der letzte vollständige Zeitraum aktiv."
                    )

                st.divider()

            if enable_first_loan_toggle:
                st.markdown("**⚙️ Optionen**")

                st.toggle(
                    "Ohne Verlängerungen",
                    key=f"{prefix}_first_loan",
                    help=(
                        "Zeigt nur Erstausleihen bzw. "
                        "Datensätze ohne Verlängerung."
                    ),
                )

                st.divider()

            if extra_filters_config:
                for col, key_ms in extra_filter_keys.items():
                    label = next(
                        (
                            conf["label"]
                            for conf in extra_filters_config
                            if conf["col"] == col
                        ),
                        col,
                    )

                    values = sorted(
                        df_extra[col]
                        .dropna()
                        .astype(str)
                        .unique()
                    )

                    st.multiselect(
                        label,
                        options=values,
                        key=key_ms,
                        placeholder="Alle",
                    )

    # --------------------------------------------------------
    # Medienbestand
    # --------------------------------------------------------

    catalog_filters = {}

    if has_catalog and catalog_filters_config:
        with st.sidebar.expander(
            expander_labels.get("catalog", "📚 Medienbestand"),
            expanded=expander_defaults.get("catalog", False),
        ):
            for conf in catalog_filters_config:
                col = conf["col"]

                if col not in df_catalog.columns:
                    continue

                value = _render_catalog_filter(
                    df_catalog,
                    conf,
                    prefix,
                )

                catalog_filters[col] = value

    # --------------------------------------------------------
    # URL-Synchronisierung
    # --------------------------------------------------------

    def set_param_safe(key, value):
        try:
            if value and str(value).strip() and len(str(value)) < 1500:
                st.query_params[key] = str(value)
            elif key in st.query_params:
                del st.query_params[key]
        except Exception:
            pass

    set_param_safe(
        "groups",
        ",".join(map(str, sel_grp)) if sel_grp else "",
    )

    set_param_safe(
        "gender",
        ",".join(map(str, sel_gen)) if sel_gen else "",
    )

    set_param_safe(
        "age_min",
        str(sel_age[0]),
    )

    set_param_safe(
        "age_max",
        str(sel_age[1]),
    )

    set_param_safe(
        "location",
        ",".join(map(str, sel_loc)) if sel_loc else "",
    )

    set_param_safe(
        "ss",
        ",".join(map(str, sel_ss)) if sel_ss else "",
    )

    if date_range_val and isinstance(date_range_val, tuple):
        set_param_safe(
            "date_start",
            str(date_range_val[0]),
        )
        set_param_safe(
            "date_end",
            str(date_range_val[1]),
        )

    if has_extra and enable_first_loan_toggle:
        first_loan_value = st.session_state.get(
            f"{prefix}_first_loan",
            True,
        )
        set_param_safe(
            "first_loan",
            "1" if first_loan_value else "",
        )

    if extra_filters_config:
        for col in extra_filter_keys:
            values = st.session_state.get(
                extra_filter_keys[col],
                [],
            )

            set_param_safe(
                f"ex_{col}",
                ",".join(map(str, values)) if values else "",
            )

    # --------------------------------------------------------
    # 3. Benutzerfilter anwenden
    # --------------------------------------------------------

    df_res = df_for_filter.copy()

    if sel_grp and group_col:
        df_res = df_res[
            df_res[group_col]
            .astype(str)
            .isin([str(v) for v in sel_grp])
        ]

    if sel_gen:
        df_res = df_res[
            df_res["Geschlecht_Filter"]
            .isin(sel_gen)
        ]

    if "Geburtsdatum" in df_res.columns:
        df_res = df_res[
            df_res["Alter_Berechnet"].between(
                sel_age[0],
                sel_age[1],
            )
        ]

    if sel_ss:
        df_res = df_res[
            df_res["SS_Kategorie"].isin(sel_ss)
        ]

    if sel_loc and loc_col:
        df_res = df_res[
            df_res[loc_col]
            .astype(str)
            .isin([str(v) for v in sel_loc])
        ]

    # --------------------------------------------------------
    # 4. Ausleihfilter anwenden
    # --------------------------------------------------------

    df_extra_res = None

    if has_extra:
        df_extra_res = df_extra.copy()

        if (
            enable_date_filter
            and date_range_val
            and isinstance(date_range_val, tuple)
            and len(date_range_val) == 2
            and date_col_name in df_extra_res.columns
        ):
            dates = pd.to_datetime(
                df_extra_res[date_col_name],
                errors="coerce",
            )

            mask = (
                dates.dt.date >= date_range_val[0]
            ) & (
                dates.dt.date <= date_range_val[1]
            )

            df_extra_res = df_extra_res[mask]

        if extra_filter_keys:
            for col, key_ms in extra_filter_keys.items():
                values = st.session_state.get(
                    key_ms,
                    [],
                )

                if values and col in df_extra_res.columns:
                    df_extra_res = df_extra_res[
                        df_extra_res[col]
                        .astype(str)
                        .isin([str(v) for v in values])
                    ]

        if enable_first_loan_toggle:
            first_loan_value = st.session_state.get(
                f"{prefix}_first_loan",
                True,
            )

            if (
                first_loan_value
                and first_loan_col_name in df_extra_res.columns
            ):
                df_extra_res = df_extra_res[
                    df_extra_res[first_loan_col_name]
                ]

        # Nur Ausleihen der gefilterten Benutzer behalten
        if (
            "Nummer" in df_res.columns
            and "Ausleihperson" in df_extra_res.columns
        ):
            user_ids = (
                df_res["Nummer"]
                .dropna()
                .astype(str)
                .unique()
            )

            df_extra_res["Ausleihperson"] = (
                df_extra_res["Ausleihperson"]
                .astype(str)
            )

            df_extra_res = df_extra_res[
                df_extra_res["Ausleihperson"]
                .isin(user_ids)
            ]

    # --------------------------------------------------------
    # Ergebnisanzeige
    # --------------------------------------------------------

    st.sidebar.divider()

    if show_metrics:
        if df_extra_res is not None:
            st.sidebar.caption(
                f"📊 Ergebnisse: {len(df_res):,} / "
                f"{len(df_extra_res):,} Transaktionen"
            )
        else:
            st.sidebar.caption(
                f"📊 Ergebnisse: {len(df_res):,}"
            )

    # --------------------------------------------------------
    # Filter-State
    # --------------------------------------------------------

    extra_filters = {}

    for col in extra_filter_keys:
        extra_filters[col] = st.session_state.get(
            extra_filter_keys[col],
            [],
        )

    return df_res, df_extra_res, {
        "groups": sel_grp,
        "gender": sel_gen,
        "age_range": sel_age,
        "locations": sel_loc,
        "ss_filter": sel_ss,
        "date_range": date_range_val,
        "first_loan_only": (
            st.session_state.get(
                f"{prefix}_first_loan",
                True,
            )
            if has_extra
            else False
        ),
        "group_col": group_col,
        "gender_col": "Geschlecht_Filter",
        "age_col": "Alter_Berechnet",
        "location_col": loc_col,
        "extra_filters": extra_filters,
        "catalog_filters": catalog_filters,
    }


# ============================================================
# ALTE FILTERFUNKTION
# ============================================================

def apply_filters(
    df,
    date_range,
    selected_zweigstellen,
    selected_medienarten,
    selected_benutzergruppen,
    selected_kategorie_alter,
    nur_erstausleihen=False,
):
    """
    Kompatibilitätsfunktion für ältere Seiten.

    Neue Seiten sollten get_sidebar_filters() verwenden.
    """
    if df is None or df.empty:
        return df

    filtered = df.copy()

    if nur_erstausleihen:
        if "Verlängerung_Anz" in filtered.columns:
            numeric = pd.to_numeric(
                filtered["Verlängerung_Anz"],
                errors="coerce",
            ).fillna(0)

            filtered = filtered[numeric == 0]
        else:
            st.warning(
                "Feld 'Verlängerung_Anz' nicht gefunden. "
                "Filter kann nicht angewendet werden."
            )

    if (
        date_range
        and len(date_range) == 2
        and "Ausleihdatum" in filtered.columns
    ):
        dates = pd.to_datetime(
            filtered["Ausleihdatum"],
            errors="coerce",
        )

        start_date = pd.to_datetime(date_range[0])
        end_date = pd.to_datetime(date_range[1])

        filtered = filtered[
            (dates >= start_date)
            & (dates <= end_date)
        ]

    if (
        selected_zweigstellen
        and "Zweigstelle" in filtered.columns
    ):
        filtered = filtered[
            filtered["Zweigstelle"]
            .astype(str)
            .isin([str(v) for v in selected_zweigstellen])
        ]

    if (
        selected_medienarten
        and "Medienart" in filtered.columns
    ):
        filtered = filtered[
            filtered["Medienart"]
            .astype(str)
            .isin([str(v) for v in selected_medienarten])
        ]

    if selected_benutzergruppen:
        target_col = "Benutzergruppe"

        if target_col in filtered.columns:
            filtered = filtered[
                filtered[target_col]
                .astype(str)
                .isin([str(v) for v in selected_benutzergruppen])
            ]
        else:
            st.warning(
                f"Spalte '{target_col}' nicht gefunden."
            )

    if (
        selected_kategorie_alter
        and "Kategorie Alter" in filtered.columns
    ):
        filtered = filtered[
            filtered["Kategorie Alter"]
            .astype(str)
            .isin([str(v) for v in selected_kategorie_alter])
        ]

    return filtered


# ============================================================
# FILTER-SETTINGS
# ============================================================

def get_filter_settings(
    date_range,
    sel_zweig,
    sel_medien,
    sel_gruppe,
    sel_alter,
    nur_erstausleihen,
):
    """Erstellt ein zentrales Filterobjekt."""
    return {
        "date_range": date_range,
        "zweigstelle": sel_zweig,
        "medienart": sel_medien,
        "benutzergruppe": sel_gruppe,
        "alter": sel_alter,
        "erstausleihen": nur_erstausleihen,
    }


# ============================================================
# GEWÄHLTE KATALOGFILTER AUF KATALOG ANWENDEN
# ============================================================

def _apply_catalog_filters(df_books, catalog_filters):
    """Wendet die typisierten Katalogfilter auf den Katalog an."""

    if df_books is None:
        return pd.DataFrame()

    filtered = df_books.copy()

    # --------------------------------------------------------
    # Multiselect-Filter
    # --------------------------------------------------------

    for col, values in catalog_filters.items():
        if col not in filtered.columns:
            continue

        if not isinstance(values, list):
            continue

        if values:
            filtered = filtered[
                filtered[col]
                .astype(str)
                .isin([str(v) for v in values])
            ]

    # --------------------------------------------------------
    # Preis / Range
    # --------------------------------------------------------

    for col, value in catalog_filters.items():
        if col not in filtered.columns:
            continue

        if not isinstance(value, tuple) or len(value) != 2:
            continue

        # Nur anwenden, wenn es sich um numerische Daten handelt
        numeric = pd.to_numeric(
            filtered[col],
            errors="coerce",
        )

        if numeric.notna().any():
            minimum, maximum = value

            filtered = filtered[
                numeric.between(minimum, maximum)
            ]

    # --------------------------------------------------------
    # Datum der Aufnahme
    # --------------------------------------------------------

    option = catalog_filters.get(
        "Datum der Aufnahme",
        "Alle Medien",
    )

    if (
        option
        and option != "Alle Medien"
        and "Datum der Aufnahme" in filtered.columns
    ):
        dates = pd.to_datetime(
            filtered["Datum der Aufnahme"],
            errors="coerce",
        )

        heute = pd.Timestamp.today().normalize()

        if option == "Aktuelles Jahr":
            filtered = filtered[
                dates.dt.year == heute.year
            ]

        elif option == "Letzte 365 Tage":
            filtered = filtered[
                dates >= heute - pd.Timedelta(days=365)
            ]

        elif option == "Letzte 2 Jahre":
            filtered = filtered[
                dates >= heute - pd.Timedelta(days=730)
            ]

    return filtered


# ============================================================
# GESAMTE GEFILTERTE DATEN AUFBAUEN
# ============================================================

def build_filtered_data(
    data,
    filtered_users,
    filtered_loans,
    filter_state,
):
    """
    Baut alle benötigten DataFrames auf Basis der Filter auf.

    Wichtig:
    Katalogfilter werden zuerst auf den Katalog angewendet.
    Anschliessend werden nur Ausleihen der gefilterten Medien
    übernommen. Dadurch wirken Lieferant, Preis und
    Neuanschaffung auch auf Ausleihanalysen.
    """

    df_users_all = (
        data.get("users", pd.DataFrame()).copy()
        if data.get("users") is not None
        else pd.DataFrame()
    )
    df_books_all = (
        data.get("catalog", pd.DataFrame()).copy()
        if data.get("catalog") is not None
        else pd.DataFrame()
    )
    df_smart = (
        data.get("smartlibrary", pd.DataFrame()).copy()
        if data.get("smartlibrary") is not None
        else pd.DataFrame()
    )

    df_loans = (
        filtered_loans.copy()
        if filtered_loans is not None
        else pd.DataFrame()
    )

    df_users = (
        filtered_users.copy()
        if filtered_users is not None
        else pd.DataFrame()
    )

    # --------------------------------------------------------
    # 1. Katalogfilter
    # --------------------------------------------------------

    catalog_filters = filter_state.get(
        "catalog_filters",
        {},
    )

    df_books_all = _apply_catalog_filters(
        df_books_all,
        catalog_filters,
    )

    # --------------------------------------------------------
    # 2. Ausleihen auf gefilterte Medien beschränken
    # --------------------------------------------------------

    if (
        "NR Zugang" in df_books_all.columns
        and "NR Zugang" in df_loans.columns
    ):
        aktive_medien = set(
            df_books_all["NR Zugang"]
            .dropna()
            .apply(normalize_media_id)
        )

        df_loans["NR Zugang"] = df_loans["NR Zugang"].astype(str)

        df_loans = df_loans[
            df_loans["NR Zugang"].apply(normalize_media_id).isin(aktive_medien)
        ]

    # --------------------------------------------------------
    # 3. Ausgeliehene Medien
    # --------------------------------------------------------

    if (
        "NR Zugang" in df_books_all.columns
        and "NR Zugang" in df_loans.columns
    ):
        aktive_medien = set(
            df_loans["NR Zugang"]
            .dropna()
            .apply(normalize_media_id)
        )

        df_books_used = df_books_all[
            df_books_all["NR Zugang"]
            .apply(normalize_media_id)
            .isin(aktive_medien)
        ].copy()
    else:
        df_books_used = df_books_all.iloc[0:0].copy()

    # --------------------------------------------------------
    # 4. Ausleihen OHNE Datumsfilter
    # --------------------------------------------------------

    df_loans_no_date = (
        data.get("loans", pd.DataFrame()).copy()
        if data.get("loans") is not None
        else pd.DataFrame()
    )

    # Nur Benutzer übernehmen, die durch die
    # Benutzerfilter übrig bleiben.
    if (
        "Nummer" in df_users.columns
        and "Ausleihperson" in df_loans_no_date.columns
    ):
        aktive_benutzer = (
            df_users["Nummer"]
            .dropna()
            .astype(str)
            .unique()
        )

        df_loans_no_date["Ausleihperson"] = (
            df_loans_no_date["Ausleihperson"]
            .astype(str)
        )

        df_loans_no_date = df_loans_no_date[
            df_loans_no_date["Ausleihperson"]
            .isin(aktive_benutzer)
        ]

    # --------------------------------------------------------
    # 5. Ausleihfilter OHNE Datumsfilter
    # --------------------------------------------------------

    extras = filter_state.get(
        "extra_filters",
        {},
    )

    for col, values in extras.items():
        if (
            values
            and col in df_loans_no_date.columns
        ):
            df_loans_no_date = df_loans_no_date[
                df_loans_no_date[col]
                .astype(str)
                .isin([str(v) for v in values])
            ]

    if filter_state.get("first_loan_only", False):
        if (
            "Erstausleihe" not in df_loans_no_date.columns
            and "Verlängerung_Anz" in df_loans_no_date.columns
        ):
            extension_count = pd.to_numeric(
                df_loans_no_date["Verlängerung_Anz"].replace("", pd.NA),
                errors="coerce",
            ).fillna(0)
            df_loans_no_date["Erstausleihe"] = extension_count == 0

        if "Erstausleihe" in df_loans_no_date.columns:
            df_loans_no_date = df_loans_no_date[
                df_loans_no_date["Erstausleihe"]
            ]

    # --------------------------------------------------------
    # 6. Katalogfilter ebenfalls auf loans_no_date anwenden
    # --------------------------------------------------------

    if (
        "NR Zugang" in df_books_all.columns
        and "NR Zugang" in df_loans_no_date.columns
    ):
        aktive_medien = set(
            df_books_all["NR Zugang"]
            .dropna()
            .apply(normalize_media_id)
        )

        df_loans_no_date["NR Zugang"] = (
            df_loans_no_date["NR Zugang"]
            .astype(str)
        )

        df_loans_no_date = df_loans_no_date[
            df_loans_no_date["NR Zugang"]
            .apply(normalize_media_id)
            .isin(aktive_medien)
        ]

    # --------------------------------------------------------
    # 7. Rückgabe
    # --------------------------------------------------------

    return {
        "loans": df_loans,
        "loans_no_date": df_loans_no_date,
        "users": df_users,
        "users_all": df_users_all,
        "books": df_books_all,
        "books_used": df_books_used,
        "smart": df_smart,
    }
