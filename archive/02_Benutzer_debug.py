import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
from pathlib import Path
import warnings
import numpy as np

warnings.filterwarnings('ignore')

from utils import load_data, load_swiss_locations, validate_and_clean_locations, run_validation_pipeline, load_shapefile_cached

st.set_page_config(page_title="Benutzer Analyse", page_icon="👥", layout="wide")
st.title("👥 Benutzer- und Zielgruppenanalyse")

# ==============================================================================
# 1. OPTIMIERTES LADEN & VALIDIEREN
# ==============================================================================

# 1. Rohdaten laden
data = load_data()
if not data:
    st.error("Keine Daten geladen.")
    st.stop()

df_ausleihe = data.get("loans")
df_users = data.get("users")

if df_users is None or df_users.empty:
    st.warning("Keine Nutzerdaten verfügbar.")
    st.stop()

# 2. Referenzdaten laden (Amtliches Ortschaftenverzeichnis mit PLZ & BFS-Nr)
# Erwartete Spalten in der CSV: 'PLZ', 'BFS_NR' (oder 'GEMDE'), 'ORTSCHAFT'
df_swiss = load_swiss_locations("data/swiss_locations.csv")

# 3. Validierung durchführen (für Datenqualität-Anzeige)
if df_swiss is not None:
    df_users, location_errors = run_validation_pipeline(df_users, df_swiss)
else:
    st.warning("Referenzdaten (swiss_locations.csv) fehlen. Datenqualität kann nicht geprüft werden.")
    df_users['Ort_Validiert'] = df_users.get('Wohnort', 'Unbekannt')
    df_users['Kanton'] = None
    df_users['Ort_Match_Status'] = '⚠️ Keine Referenzdaten'
    location_errors = pd.DataFrame()

# --- Sidebar Filter ---
st.sidebar.header("Filter")

group_col = "Benutzergruppe_Gruppiert" if "Benutzergruppe_Gruppiert" in df_users.columns else "Benutzergruppe"
unique_groups = sorted(df_users[group_col].dropna().unique())
selected_groups = st.sidebar.multiselect("Benutzergruppe", options=unique_groups, default=unique_groups)

unique_kantone = sorted(df_users['Kanton'].dropna().unique()) if 'Kanton' in df_users.columns else []
selected_kantone = st.sidebar.multiselect("Kanton", options=unique_kantone, default=unique_kantone) if unique_kantone else None

# Filter anwenden
df_filtered = df_users.copy()
if selected_groups:
    df_filtered = df_filtered[df_filtered[group_col].isin(selected_groups)]
if selected_kantone and 'Kanton' in df_filtered.columns:
    df_filtered = df_filtered[df_filtered['Kanton'].isin(selected_kantone)]

st.info(f"Zeige Daten für **{len(df_filtered):,}** Nutzer:innen (nach Filter).")

# ==============================================================================
# 2. DEMOGRAFISCHE ANALYSE
# ==============================================================================

c1, c2 = st.columns(2)
with c1:
    st.subheader("Verteilung nach Benutzergruppe")
    if group_col in df_filtered.columns:
        data_grp = df_filtered[group_col].fillna("Unbekannt").value_counts().reset_index()
        data_grp.columns = ["Gruppe", "Anzahl"]
        st.bar_chart(data_grp, x="Gruppe", y="Anzahl", color="Gruppe")

with c2:
    st.subheader("Verteilung nach Kanton")
    if 'Kanton' in df_filtered.columns and df_filtered['Kanton'].notna().any():
        data_kt = df_filtered['Kanton'].value_counts().reset_index()
        data_kt.columns = ["Kanton", "Anzahl"]
        st.bar_chart(data_kt, x="Kanton", y="Anzahl", color="Kanton")
    else:
        st.caption("Keine Kantonsdaten verfügbar.")

st.divider()

# ==============================================================================
# 3. GEO-ANALYSE & DATENQUALITÄT (4-STUFEN-MODELL)
# ==============================================================================

st.subheader("🗺️ Geografische Verteilung & Datenqualität")

STATUS_OK = '✅ OK'
STATUS_CORRECTED_LIST = ['⚠️ Korrigiert', '⚠️ Ort korrigiert', '⚠️ PLZ korrigiert']
STATUS_UNKNOWN = '❌ Unbekannt'

# Unvollständigkeit prüfen
mask_incomplete = (
    df_filtered['PLZ'].isna() | 
    (df_filtered['PLZ'].astype(str).str.strip() == '') | 
    (df_filtered['PLZ'].astype(str).str.lower() == 'nan') |
    df_filtered['Wohnort'].isna() | 
    (df_filtered['Wohnort'].astype(str).str.strip() == '') |
    (df_filtered['Wohnort'].astype(str).str.lower() == 'nan')
)
count_incomplete = mask_incomplete.sum()

# Match Status prüfen
df_complete = df_filtered[~mask_incomplete].copy()

mask_ok = df_complete['Ort_Match_Status'] == STATUS_OK
count_ok = mask_ok.sum()

mask_corrected = df_complete['Ort_Match_Status'].isin(STATUS_CORRECTED_LIST)
count_corr = mask_corrected.sum()

mask_unknown = df_complete['Ort_Match_Status'] == STATUS_UNKNOWN
count_unknown = mask_unknown.sum()

total_users = len(df_filtered)
match_rate = ((count_ok + count_corr) / total_users * 100) if total_users > 0 else 0

# Metriken anzeigen
c1, c2, c3, c4 = st.columns(4)
c1.metric("✅ Zugeordnet", f"{count_ok + count_corr:,}", f"{match_rate:.1f}%")
c2.metric("🛠️ Korrigiert", f"{count_corr:,}", "Automatisch bereinigt")

if count_unknown > 0:
    c3.metric("❌ Fehlerhaft", f"{count_unknown:,}", "Unbekannter Ort", delta_color="inverse")
else:
    c3.metric("❌ Fehlerhaft", "0", "-")

if count_incomplete > 0:
    c4.metric("⚪ Unvollständig", f"{count_incomplete:,}", "Kein Ort/PLZ", delta_color="inverse")
else:
    c4.metric("⚪ Unvollständig", "0", "-")

# Details in Tabs
if count_unknown > 0 or count_incomplete > 0 or count_corr > 0:
    st.divider()
    labels = []
    if count_unknown > 0: labels.append("❌ Fehlerhafte Orte")
    if count_incomplete > 0: labels.append("⚪ Fehlende Daten")
    if count_corr > 0: labels.append("🛠️ Autom. Korrekturen")
    
    tabs = st.tabs(labels)
    idx = 0

    if count_unknown > 0:
        with tabs[idx]:
            st.warning(f"**{count_unknown}** Datensätze haben eine ungültige PLZ/Ort-Kombination.")
            df_problems = df_complete[mask_unknown]
            df_problems['Kombi'] = df_problems['PLZ'].astype(str) + " | " + df_problems['Wohnort'].astype(str)
            top_errors = df_problems['Kombi'].value_counts().head(10).reset_index()
            top_errors.columns = ["Eingegebene Kombination", "Anzahl"]
            st.dataframe(top_errors, hide_index=True, use_container_width=True)
            st.info("💡 **Ursache:** Tippfehler oder Ausland. Bitte in BiThek korrigieren.")
        idx += 1

    if count_incomplete > 0:
        with tabs[idx]:
            st.info(f"**{count_incomplete}** Datensätze haben keine PLZ oder keinen Wohnort.")
            m_plz = df_filtered[mask_incomplete & (df_filtered['PLZ'].isna() | (df_filtered['PLZ'].astype(str).str.strip() == ''))].shape[0]
            m_ort = df_filtered[mask_incomplete & (df_filtered['Wohnort'].isna() | (df_filtered['Wohnort'].astype(str).str.strip() == ''))].shape[0]
            cm1, cm2 = st.columns(2)
            cm1.metric("Davon ohne PLZ", m_plz)
            cm2.metric("Davon ohne Wohnort", m_ort)
            
            with st.expander("Betroffene Benutzergruppen anzeigen"):
                distro = df_filtered[mask_incomplete][group_col].value_counts().head(10).reset_index()
                distro.columns = ["Benutzergruppe", "Anzahl"]
                st.bar_chart(distro, x="Benutzergruppe", y="Anzahl", color="Benutzergruppe")
                st.dataframe(distro, hide_index=True, use_container_width=True)
            st.info("💡 **Ursache:** Oft Testaccounts oder unvollständige Registrierung.")
        idx += 1

    if count_corr > 0:
        with tabs[idx]:
            st.success(f"**{count_corr}** Einträge wurden automatisch bereinigt.")
            df_corr = df_complete[mask_corrected][['PLZ', 'Wohnort', 'Ort_Validiert']].drop_duplicates().head(15)
            st.dataframe(df_corr.rename(columns={"Wohnort": "Original", "Ort_Validiert": "Korrektur"}), hide_index=True, use_container_width=True)
            st.caption("Empfehlung: Stammdaten in BiThek nachpflegen.")
        idx += 1
else:
    st.divider()
    st.success("🎉 Perfekte Datenqualität! Alle Nutzer wurden erfolgreich zugeordnet.")

# ==============================================================================
# 4. KARTE (LOOKUP ÜBER ORTSNAME -> BFS-NR)
# ==============================================================================

st.divider()
st.subheader("🗺️ Karte der Nutzer:innen")

# 0. REFERENZDATEI EXPLIZIT NEU LADEN (Um Verwechslung mit Nutzerdaten zu vermeiden)
# Wir laden die swiss_locations.csv hier frisch als reine Referenz-Tabelle.
ref_csv_path = Path("data/swiss_locations.csv")
if not ref_csv_path.exists():
    st.error("Referenzdatei 'data/swiss_locations.csv' nicht gefunden!")
    st.stop()

try:
    # Trennzeichen ist oft ';' bei Schweizer CSVs, falls Fehler beim Laden: sep=';' prüfen
    df_ref_official = pd.read_csv(ref_csv_path, sep=';', dtype=str) 
    
    # Prüfen ob die erwarteten Spalten da sind
    if 'Ortschaftsname' not in df_ref_official.columns or 'BFS-Nr' not in df_ref_official.columns:
        st.error(f"Falsches Format in swiss_locations.csv. Erwartet: 'Ortschaftsname', 'BFS-Nr'. Vorhanden: {df_ref_official.columns.tolist()}")
        st.stop()
        
    # Bereinigung der Referenz
    df_ref_official['Ortschaftsname'] = df_ref_official['Ortschaftsname'].str.strip()
    df_ref_official['BFS-Nr'] = df_ref_official['BFS-Nr'].astype(str).str.zfill(4)
    
    # Mapping Dictionary erstellen: Ort -> BFS
    ort_to_bfs = pd.Series(df_ref_official['BFS-Nr'].values, index=df_ref_official['Ortschaftsname']).to_dict()
    
    st.caption(f"ℹ️ Offizielle Referenz geladen: {len(ort_to_bfs)} Einträge.")

except Exception as e:
    st.error(f"Fehler beim Laden der Referenz-CSV: {e}")
    st.stop()
st.divider()

# 1. SHAPEFILE LADEN
data_dir = Path('data/swissboundaries3d')
shp_file = None
if data_dir.exists():
    gemeinde_files = list(data_dir.glob('*Gemeinde*.shp'))
    if gemeinde_files: shp_file = gemeinde_files[0]
    else:
        hoheits_files = list(data_dir.glob('*Hoheitsgebiet*.shp'))
        if hoheits_files: shp_file = hoheits_files[0]

if not shp_file:
    possible_files = list(Path('.').rglob('*.shp'))
    if possible_files: shp_file = possible_files[0]
    else:
        st.error("Keine Shapefile gefunden.")
        st.stop()

try:
    gdf = load_shapefile_cached(str(shp_file))
    
    # Shapefile Spalten zuweisen
    bfs_col_shp = 'BFS_NUMMER'
    name_col = 'NAME'
    
    if bfs_col_shp not in gdf.columns:
        st.error(f"Spalte {bfs_col_shp} nicht im Shapefile gefunden!")
        st.stop()

    gdf_clean = gdf[[bfs_col_shp, name_col, 'geometry']].copy()
    gdf_clean.rename(columns={bfs_col_shp: 'bfs_nr', name_col: 'gemeinde_name'}, inplace=True)
    
    # BFS-Nummer zu 4-stelligem String machen
    gdf_clean['bfs_nr'] = gdf_clean['bfs_nr'].astype(str).str.zfill(4)
    gdf_clean = gdf_clean.drop_duplicates(subset=['bfs_nr'])
    
    if gdf_clean.crs.to_epsg() != 4326:
        gdf_clean = gdf_clean.to_crs("EPSG:4326")

# ... (Nach dem Laden der Referenz-CSV und Shapefile) ...

    # 2. NUTZERDATEN VORBEREITEN
    df_map = df_complete[mask_ok | mask_corrected].copy()
    
    # Spalte für den Namen-Lookup wählen
    if 'Ort_Norm' in df_map.columns:
        lookup_col = 'Ort_Norm'
    elif 'Ort_Validiert' in df_map.columns:
        lookup_col = 'Ort_Validiert'
    else:
        st.error("Keine gültige Ort-Spalte gefunden.")
        st.stop()

    df_map['ort_lookup'] = df_map[lookup_col].astype(str).str.strip()
    
    # PLZ bereinigen (nur Ziffern, 4-stellig)
    df_map['plz_clean'] = df_map['PLZ'].astype(str).str.extract('(\d{4})')[0] # Extrahiere 4 Ziffern

    # 3. LOOKUP DURCHFÜHREN (MIT BERÜCKSICHTIGUNG DES ADRESSANTEILS)

    # --- SCHRITT 0: REFERENZDATEN BEREINIGEN (MIT KORREKTEM SPALTENNAMEN) ---
    
    st.caption("ℹ️ Bereinige Referenzdaten: Nutze nur die Hauptgemeinde (höchster Adressenanteil) pro PLZ/Ort.")

    # 1. Adressenanteil bereinigen (Prozentzeichen entfernen, zu Float konvertieren)
    # ACHTUNG: Spaltenname ist 'Adressenanteil' (mit 'en')!
    df_ref_official['Adressenanteil_Num'] = df_ref_official['Adressenanteil'].str.replace('%', '').str.replace(',', '.').astype(float)
    
    # 2. Für PLZ-Lookup: Gruppiere nach PLZ4 und behalte nur die Zeile mit dem max. Adressenanteil
    idx_max_plz = df_ref_official.groupby('PLZ4')['Adressenanteil_Num'].idxmax()
    df_ref_plz_clean = df_ref_official.loc[idx_max_plz].copy()
    
    # 3. Für Namens-Lookup: Gruppiere nach Ortschaftsname und behalte nur die Zeile mit dem max. Adressenanteil
    idx_max_name = df_ref_official.groupby('Ortschaftsname')['Adressenanteil_Num'].idxmax()
    df_ref_name_clean = df_ref_official.loc[idx_max_name].copy()
    
    st.success(f"✅ Referenzdaten bereinigt: {len(df_ref_plz_clean)} eindeutige PLZs, {len(df_ref_name_clean)} eindeutige Orte.")
    
    # Debug: Prüfe Aesch LU explizit
    aesch_check = df_ref_official[df_ref_official['Ortschaftsname'] == 'Aesch LU']
    if not aesch_check.empty:
        best_aesch = aesch_check.loc[aesch_check['Adressenanteil_Num'].idxmax()]
        st.write(f"🔍 Check Aesch LU: Beste Zuordnung ist PLZ {best_aesch['PLZ4']} -> BFS {best_aesch['BFS-Nr']} ({best_aesch['Gemeindename']}) mit {best_aesch['Adressenanteil']} Anteil.")

    # --- SCHRITT A: Lookup über Namen (mit bereinigter Tabelle) ---
    df_ref_name_clean['BFS-Nr_Str'] = df_ref_name_clean['BFS-Nr'].astype(str).str.zfill(4)
    ort_to_bfs = pd.Series(df_ref_name_clean['BFS-Nr_Str'].values, index=df_ref_name_clean['Ortschaftsname']).to_dict()
    
    df_map['bfs_nr'] = df_map['ort_lookup'].map(ort_to_bfs)
    count_name_match = df_map['bfs_nr'].notna().sum()
    
    # --- SCHRITT B: Fallback über PLZ (mit bereinigter Tabelle) ---
    mask_missing = df_map['bfs_nr'].isna() & df_map['plz_clean'].notna()
    
    if mask_missing.any():
        df_ref_plz_clean['BFS-Nr_Str'] = df_ref_plz_clean['BFS-Nr'].astype(str).str.zfill(4)
        df_ref_plz_clean['PLZ4_Str'] = df_ref_plz_clean['PLZ4'].astype(str).str.zfill(4)
        
        # Prüfe auf Mehrdeutigkeit (sollte jetzt minimal sein)
        plz_counts = df_ref_plz_clean.groupby('PLZ4_Str')['BFS-Nr_Str'].nunique()
        ambiguous_plzs = plz_counts[plz_counts > 1].index.tolist()
        
        unique_plz_map = df_ref_plz_clean[~df_ref_plz_clean['PLZ4_Str'].isin(ambiguous_plzs)]
        plz_to_bfs = pd.Series(unique_plz_map['BFS-Nr_Str'].values, index=unique_plz_map['PLZ4_Str']).to_dict()
        
        df_map.loc[mask_missing, 'bfs_nr'] = df_map.loc[mask_missing, 'plz_clean'].map(plz_to_bfs)
        
        count_plz_match = df_map['bfs_nr'].notna().sum() - count_name_match
        if count_plz_match > 0:
            st.success(f"✅ Zusätzliche {count_plz_match} Orte über PLZ (Hauptgemeinde) zugeordnet!")

    # ... (Restlicher Code: Statistik, Merge, Plotting bleibt unverändert) ...
    # Aber jetzt sollten die BFS-Nummern korrekt sein (Aesch LU = 1021 statt 1041)!

    # ==============================================================================
    # DEBUGGING & ANALYSE
    # ==============================================================================
    st.divider()
    st.subheader("🔍 Forensik: Woher kommen die Leutwil-Nutzer?")

    # 1. Finde die BFS-Nummer von Leutwil in der Referenz-CSV
    leutwil_ref = df_ref_official[df_ref_official['Ortschaftsname'].str.contains('Leutwil', case=False, na=False)]
    st.write("Leutwil in der Referenz-CSV:")
    st.dataframe(leutwil_ref[['Ortschaftsname', 'PLZ4', 'BFS-Nr', 'Gemeindename']])

    if not leutwil_ref.empty:
        leutwil_bfs = leutwil_ref['BFS-Nr'].iloc[0] # Annahme: Es gibt nur eine Haupt-BFS für Leutwil
        st.write(f"Ziel-BFS für Leutwil: **{leutwil_bfs}**")
        
        # 2. Prüfe, welche Nutzer im Dataset diese BFS-Nr bekommen haben
        df_leutwil_users = df_map[df_map['bfs_nr'] == str(leutwil_bfs).zfill(4)]
        
        st.write(f"Anzahl Nutzer mit BFS {leutwil_bfs}: **{len(df_leutwil_users)}**")
        
        if len(df_leutwil_users) > 0:
            st.write("Herkunft dieser Nutzer (Ort & PLZ):")
            st.dataframe(
                df_leutwil_users.groupby(['ort_lookup', 'plz_clean']).size().reset_index(name='Anzahl'),
                hide_index=True
            )
            
            # Analyse
            unique_origins = df_leutwil_users['ort_lookup'].unique()
            if len(unique_origins) > 1:
                st.warning(f"⚠️ **ALARM:** Nutzer aus {len(unique_origins)} verschiedenen Orten wurden Leutwil zugeordnet!")
                st.write("Das deutet auf einen Fehler im PLZ-Fallback oder im Merge hin.")
                st.write("Betroffene Orte:", unique_origins)
            else:
                st.success("Alle zugeordneten Nutzer kommen tatsächlich aus Leutwil (oder einem Ort, der korrekt als Leutwil identifiziert wurde).")
                
            # 3. Prüfe die "vermissten" Aesch-Nutzer
            # Sind Aesch-Nutzer vielleicht fälschlicherweise in der Leutwil-Gruppe?
            aesch_in_leutwil = df_leutwil_users[df_leutwil_users['ort_lookup'].str.contains('Aesch', case=False, na=False)]
            if not aesch_in_leutwil.empty:
                st.error(f"🚨 **FUND:** {len(aesch_in_leutwil)} Nutzer aus 'Aesch' wurden fälschlicherweise Leutwil zugeordnet!")
                st.write("Details:")
                st.dataframe(aesch_in_leutwil[['ort_lookup', 'plz_clean', 'bfs_nr']])
                st.info("Ursache: Wahrscheinlich eine mehrdeutige PLZ, die im Fallback falsch aufgelöst wurde.")
        total = len(df_map)
    missing_final = df_map['bfs_nr'].isna().sum()
    success_rate = ((total - missing_final) / total * 100) if total > 0 else 0
    
    st.caption(f"✅ Insgesamt {total - missing_final:,} von {total:,} Nutzern zugeordnet ({success_rate:.1f}%).")

# --- SPEZIFISCHES DEBUGGING FÜR "AESCH" ---
    # Prüfe alle Nutzer, die "Aesch" im Namen haben oder eine der typischen PLZs
    # (Du kannst die PLZ-Liste erweitern, wenn du andere spezifische Fälle hast)
    known_aesch_plz = ['4147', '6285', '8954'] 
    df_suspect = df_map[
        df_map['ort_lookup'].str.contains('Aesch', case=False, na=False) | 
        df_map['plz_clean'].isin(known_aesch_plz)
    ]
    
    if not df_suspect.empty:
        st.divider()
        st.subheader("🔍 Debug-Analyse: 'Aesch' und ähnliche Fälle")
        
        # Wähle die relevanten Spalten
        display_cols = ['ort_lookup', 'plz_clean', 'bfs_nr']
        if 'Ort_Validiert' in df_suspect.columns:
            display_cols.append('Ort_Validiert')
            
        st.write("Details der betroffenen Nutzer:")
        
        # Einfache Darstellung ohne komplexes Styling (vermeidet applymap Fehler)
        # Wir fügen eine Status-Spalte hinzu
        df_debug = df_suspect[display_cols].copy()
        df_debug['Status'] = df_debug['bfs_nr'].apply(lambda x: "✅ Erfolg" if pd.notna(x) else "❌ Fehlschlag")
        
        st.dataframe(df_debug, use_container_width=True)
        
        # Detaillierte Ursachenanalyse für die Fehlerhaften
        df_errors = df_debug[df_debug['Status'] == "❌ Fehlschlag"]
        
        if not df_errors.empty:
            st.info("**Warum wurden diese nicht gefunden?**")
            
            # Wir analysieren nur die ersten 5 Fehler, um den Chat nicht zu fluten
            for idx, row in df_errors.head(5).iterrows():
                ort = row['ort_lookup']
                plz = row['plz_clean']
                
                st.markdown(f"🔴 **Fall:** `{ort}` (PLZ: `{plz}`)")
                
                # 1. Check: Gibt es die PLZ in der Referenz?
                # Achtung: PLZ4 in der CSV ist evtl. Integer oder String. Wir vergleichen sicher.
                mask_plz = df_ref_official['PLZ4'].astype(str).str.zfill(4) == str(plz).zfill(4)
                ref_by_plz = df_ref_official[mask_plz]
                
                # 2. Check: Gibt es den Namen in der Referenz?
                mask_name = df_ref_official['Ortschaftsname'].str.contains(ort, case=False, na=False)
                ref_by_name = df_ref_official[mask_name]
                
                if not ref_by_plz.empty:
                    st.write(f"   - ✅ PLZ `{plz}` existiert in der Referenz.")
                    st.write(f"     Gefundene Orte: `{ref_by_plz['Ortschaftsname'].unique()}`")
                    st.write(f"     Zugehörige BFS-Nrn: `{ref_by_plz['BFS-Nr'].unique()}`")
                    
                    # Prüfen auf Mehrdeutigkeit
                    if len(ref_by_plz['BFS-Nr'].unique()) > 1:
                        st.warning(f"   ⚠️ Die PLZ ist mehrdeutig ({len(ref_by_plz)} Einträge). Der einfache PLZ-Lookup hat sie übersprungen.")
                    else:
                        st.error(f"   ❌ Obwohl die PLZ eindeutig ist, wurde kein Match erstellt. Prüfe den Code auf Logikfehler beim Mapping.")
                        
                elif not ref_by_name.empty:
                    st.write(f"   - ✅ Name `{ort}` (oder ähnlich) existiert in der Referenz.")
                    st.write(f"     Gefundene Varianten: `{ref_by_name['Ortschaftsname'].unique()}`")
                    st.warning(f"   ⚠️ Der exakte String-Match hat fehlgeschlagen. Vielleicht Leerzeichen oder Sonderzeichen?")
                else:
                    st.error(f"   ❌ Weder PLZ `{plz}` noch Name `{ort}` wurden in der Referenz-CSV gefunden.")
                    st.write("   → Mögliche Ursache: Tippfehler in beiden Feldern oder es handelt sich um eine ausländische Adresse / spezielle PLZ.")
                
                st.divider()

    # --- ALLGEMEINES DEBUGGING FÜR ALLE FEHLER ---
    if missing_final > 0:
        st.divider()
        with st.expander(f"🐞 Alle {missing_final} nicht zugeordneten Orte anzeigen"):
            st.warning("Diese konnten weder über Namen noch über PLZ zugeordnet werden:")
            
            # Gruppiere nach Ort und PLZ, um Muster zu erkennen
            df_missing = df_map[df_map['bfs_nr'].isna()][['ort_lookup', 'plz_clean']].drop_duplicates()
            st.dataframe(df_missing.head(50), hide_index=True, use_container_width=True)
            
            # Häufigste Fehler
            if not df_missing.empty:
                st.write("**Häufigste fehlende Orte:**")
                st.bar_chart(df_map[df_map['bfs_nr'].isna()]['ort_lookup'].value_counts().head(10))
                
                st.info("💡 **Tipp:** Wenn du hier 'Aesch' siehst, aber die PLZ korrekt ist (z.B. 4147), dann war der PLZ-Fallback nicht erfolgreich. Prüfe die obige Detail-Analyse.")

# ==============================================================================
    # 4. MERGE & PLOT (MIT TIEFEN-DEBUGGING)
    # ==============================================================================
    
    df_valid = df_map[df_map['bfs_nr'].notna()]
    
    if df_valid.empty:
        st.warning("Keine Daten für die Karte verfügbar.")
    else:
        # --- SCHRITT 1: AGGREGATION ---
        user_counts = df_valid.groupby('bfs_nr').size().reset_index(name='Anzahl_Kunden')
        user_counts['bfs_nr'] = user_counts['bfs_nr'].astype(str) # Sicherstellen: String
        
        st.write(f"📊 **Schritt 1: Aggregation**")
        st.write(f"   - Einträge in `user_counts`: {len(user_counts)}")
        
        # Prüfe spezifische Gemeinden
        test_bfs_list = ['1041', '4146', '4147'] # 1041=Aesch LU, 4146=Bettwil, 4147=Aesch BL (Beispiele)
        for bfs in test_bfs_list:
            if bfs in user_counts['bfs_nr'].values:
                count = user_counts[user_counts['bfs_nr'] == bfs]['Anzahl_Kunden'].iloc[0]
                st.success(f"   ✅ BFS {bfs} ist in `user_counts` mit {count} Nutzern.")
            else:
                st.error(f"   ❌ BFS {bfs} FEHLT in `user_counts`! (Problem bei der Aggregation)")

        # --- SCHRITT 2: SHAPEFILE CHECK ---
        st.write(f"🗺️ **Schritt 2: Shapefile (`gdf_clean`)**")
        st.write(f"   - Einträge in `gdf_clean`: {len(gdf_clean)}")
        st.write(f"   - Datentyp von `bfs_nr` im Shapefile: {gdf_clean['bfs_nr'].dtype}")
        
        for bfs in test_bfs_list:
            # Prüfe als String und als Int, falls Typen mismatchen
            mask = (gdf_clean['bfs_nr'] == bfs) | (gdf_clean['bfs_nr'] == int(bfs))
            if mask.any():
                name = gdf_clean[mask]['gemeinde_name'].iloc[0]
                st.success(f"   ✅ BFS {bfs} ist im Shapefile als '{name}'.")
            else:
                st.error(f"   ❌ BFS {bfs} FEHLT im Shapefile!")

        # --- SCHRITT 3: DER MERGE ---
        st.write(f"🔗 **Schritt 3: Merge**")
        merged_gdf = gdf_clean.merge(user_counts, on='bfs_nr', how='inner')
        st.write(f"   - Einträge NACH dem Merge: {len(merged_gdf)}")
        
        # Check ob die Test-Gemeinden den Merge überlebt haben
        for bfs in test_bfs_list:
            if bfs in merged_gdf['bfs_nr'].values:
                count = merged_gdf[merged_gdf['bfs_nr'] == bfs]['Anzahl_Kunden'].iloc[0]
                st.success(f"   ✅ BFS {bfs} hat den Merge überlebt! ({count} Nutzer)")
            else:
                st.error(f"   ❌ BFS {bfs} ist NACH DEM MERGE VERSCHWUNDEN!")
                st.info(f"      Ursache: Der Join-Schlüssel passt nicht. Prüfe die Datentypen oben.")

        # --- SCHRITT 4: GEOJSON INSPEKTION ---
        st.write(f"📝 **Schritt 4: GeoJSON Vorbereitung**")
        if len(merged_gdf) == 0:
            st.error("Merge war leer. Kein GeoJSON möglich.")
        else:
            geojson_data = merged_gdf.__geo_interface__
            st.write(f"   - Anzahl Features im GeoJSON: {len(geojson_data['features'])}")
            
            # Inspektion des ersten Features
            if len(geojson_data['features']) > 0:
                first_feat = geojson_data['features'][0]
                props = first_feat['properties']
                st.write(f"   - Keys im ersten Feature: {list(props.keys())}")
                
                # Suche nach unserer BFS-Nr im ersten Feature
                # Wir prüfen, ob 'bfs_nr' existiert und welchen Typ es hat
                if 'bfs_nr' in props:
                    val = props['bfs_nr']
                    st.write(f"   - Wert von 'bfs_nr' im Feature: '{val}' (Typ: {type(val).__name__})")
                else:
                    st.warning("   - 'bfs_nr' fehlt in den Properties des ersten Features!")

            # --- REPARATUR & PLOT ---
            st.divider()
            st.subheader("🛠️ Reparatur & Plotting")
            
            # Wir erzwingen den Key 'bfs_nr' als String in allen Features
            for i, feature in enumerate(geojson_data['features']):
                val = str(merged_gdf.iloc[i]['bfs_nr'])
                feature['properties']['bfs_nr'] = val
            
            # Prüfe jetzt Aesch explizit im reparierten GeoJSON
            aesch_found_in_geojson = False
            for feature in geojson_data['features']:
                if feature['properties'].get('bfs_nr') == '1041':
                    aesch_found_in_geojson = True
                    break
            
            if aesch_found_in_geojson:
                st.success("✅ Aesch (1041) wurde explizit in das GeoJSON injiziert.")
            else:
                st.error("❌ Aesch konnte nicht in das GeoJSON injiziert werden (nicht im merged_gdf?).")

            # PLOTTEN
            # Bereite die logarithmierte Spalte vor
            merged_gdf['color_log'] = np.log10(merged_gdf['Anzahl_Kunden'] + 1)

            # --- DYNAMISCHES ZENTRIEREN AUF DIE TOP-GEMEINDE ---
            top_gemeinde = merged_gdf.loc[merged_gdf['Anzahl_Kunden'].idxmax()]
            top_name = top_gemeinde['gemeinde_name']
            top_count = top_gemeinde['Anzahl_Kunden']
            
            # Hole den Mittelpunkt (Centroid) der Geometrie dieser Gemeinde
            # Wir nutzen .to_crs(4326) kurz, um Lat/Lon korrekt zu berechnen, falls das Original anders ist
            # Da merged_gdf aber schon 4326 ist (vom Shapefile her), reicht meist direct access.
            centroid = top_gemeinde.geometry.centroid
            center_lat = centroid.y
            center_lon = centroid.x
            
            st.info(f"🎯 Fokus auf **{top_name}** mit **{top_count:,}** Nutzern.")
            
            # Zoom-Level anpassen:
            # Bei sehr hohen Nutzerzahlen (grosse Stadt) wollen wir etwas weiter rauszoomen (z.B. 10)
            # Bei kleinen Zahlen etwas näher ran (z.B. 12)
            # Einfache Logik: Je mehr Nutzer, desto kleiner der Zoom (weiter weg).
            if top_count > 1000:
                dynamic_zoom = 8 #
            elif top_count > 100:
                dynamic_zoom = 9 #11
            else:
                dynamic_zoom = 10 #12

            # --- PLOTTEN ---
            fig = px.choropleth_mapbox(
                merged_gdf,
                geojson=geojson_data,
                locations="bfs_nr",
                featureidkey="properties.bfs_nr",
                color="color_log", 
                color_continuous_scale="Viridis",
                mapbox_style="carto-positron",
                zoom=dynamic_zoom, # Dynamischer Zoom
                center={"lat": center_lat, "lon": center_lon}, # Dynamisches Zentrum
                opacity=0.8,
                title=f"Nutzer:innen nach Gemeinde (Fokus: {top_name})",
                hover_name="gemeinde_name",
                hover_data={"Anzahl_Kunden": True, "color_log": False, "bfs_nr": False}
            )
            
            fig.update_layout(
                coloraxis_colorbar=dict(
                    title="Nutzer (log)",
                    tickvals=[np.log10(1), np.log10(10), np.log10(100), np.log10(1000)],
                    ticktext=["1", "10", "100", "1'000"]
                ),
                margin={"r":0, "t":50, "l":0, "b":0}, 
                height=600
            )
            
            st.plotly_chart(fig, use_container_width=True)
            st.caption("💡 Hinweis: Die Farben sind logarithmisch skaliert, damit kleine und grosse Gemeinden gleichzeitig gut sichtbar sind.")

            if not aesch_found_in_geojson:
                st.error("Da Aesch nicht im GeoJSON ist, kann es nicht angezeigt werden. Prüfe den Merge-Schritt oben.")
            else:
                st.info("Aesch ist im GeoJSON. Wenn es auf der Karte trotzdem fehlt, zoome manuell auf den Kanton Luzern (ca. 47.05, 8.2). Vielleicht ist es nur zu klein oder die Farbe ist zu hell.")
except Exception as e:
    st.error(f"Fehler bei der Kartenerstellung: {e}")
    st.code(str(e))

st.divider()

# ==============================================================================
# 5. TOP NUTZER
# ==============================================================================
st.subheader("Aktivste Nutzer-IDs (Top 20)")
st.caption("Basierend auf allen Ausleihdaten (global).")

if df_ausleihe is not None and "Ausleihperson" in df_ausleihe.columns:
    top_users = (df_ausleihe.groupby("Ausleihperson").size()
                 .reset_index(name="Ausleihen")
                 .sort_values("Ausleihen", ascending=False).head(20))
    st.dataframe(top_users, hide_index=True, use_container_width=True)
else:
    st.caption("Keine Ausleihdaten für diese Ansicht verfügbar.")