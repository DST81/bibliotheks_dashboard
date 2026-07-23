import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
from pathlib import Path
import warnings
import numpy as np

warnings.filterwarnings('ignore')

from utils import load_data, load_swiss_locations, validate_and_clean_locations, run_validation_pipeline, load_shapefile_cached
from filters import get_sidebar_filters

st.set_page_config(page_title="Benutzer Analyse", page_icon="👥", layout="wide")
st.title("👥 Benutzer- und Zielgruppenanalyse")

# ==============================================================================
# 1. DATEN AUS SESSION_STATE HOLEN (WICHTIG!)
# ==============================================================================

# Prüfen, ob Daten geladen wurden
if 'data' not in st.session_state or st.session_state['data'] is None:
    st.error("Keine Daten geladen. Bitte starten Sie das Dashboard über die [Startseite](../app.py).")
    st.stop()

# Daten aus dem globalen Speicher laden
data = st.session_state['data']

# JETZT werden die Variablen definiert:
df_ausleihe = data.get("loans")
df_users = data.get("users")
df_katalog = data.get("catalog") # Falls vorhanden

# Prüfen ob Nutzerdaten da sind
if df_users is None or df_users.empty:
    st.warning("Keine Nutzerdaten verfügbar.")
    st.stop()

# Optional: Wenn du für diese Seite auch die Ausleihdaten brauchst (z.B. für Top-Nutzer)
# und sie fehlen, kannst du hier eine Warnung ausgeben, aber den Fehler vermeiden:
if df_ausleihe is None:
    st.info("Hinweis: Keine Ausleihdaten verfügbar. Einige Analysen (z.B. Top-Nutzer) werden übersprungen.")
    # Wir setzen df_ausleihe auf einen leeren DataFrame, damit der Code unten nicht abstürzt
    df_ausleihe = pd.DataFrame()

# ==============================================================================
# 2. VALIDIERUNG (Falls noch nicht in app.py geschehen)
# ==============================================================================
# Falls du die Validierung aus app.py entfernt hast, muss sie HIER passieren.
# Falls sie in app.py läuft, sind df_users bereits die Spalten 'Ort_Validiert' etc. vorhanden.

df_swiss = None
if 'ref_swiss' in st.session_state and st.session_state['ref_swiss'] is not None:
    df_swiss = st.session_state['ref_swiss']
else:
    # Fallback: Hier laden, falls nicht im Session State
    try:
        from utils import load_swiss_locations
        df_swiss = load_swiss_locations("data/swiss_locations.csv")
        # Optional in Session State speichern für nächstes Mal
        st.session_state['ref_swiss'] = df_swiss 
    except:
        st.warning("Referenzdaten konnten nicht geladen werden.")

# Validierung durchführen, falls noch nicht geschehen (Check ob Spalte existiert)
if df_swiss is not None and 'Ort_Validiert' not in df_users.columns:
    with st.spinner('Validiere Adressen...'):
        from utils import validate_and_clean_locations
        df_users, _ = validate_and_clean_locations(df_users, df_swiss)
        # Aktualisiere auch den session_state, falls andere Seiten davon profitieren
        st.session_state['data']['users'] = df_users

# --- HIER DIE NEUE FILTER-FUNKTION AUFRUFEN ---

# Wir nutzen eine Dummy-Variable '_' für den zweiten Rückgabewert (df_extra), der hier None ist.
df_filtered, _, filter_info = get_sidebar_filters(df_users, prefix="bib_dashboard")
#st.write("DEBUG Benutzer: Groups =", filter_info.get('groups'))
#st.write("DEBUG Benutzer: URL Params =", st.query_params.to_dict())


# Der Variable 'group_col' musst du jetzt aus filter_info holen:
group_col = filter_info['group_col']

# ==============================================================================
# 2. DEMOGRAFISCHE ANALYSE (2x2 Layout)
# ==============================================================================

st.subheader("Demografische Übersicht")

# Zeile 1: Benutzergruppe & Wohnort
c1, c2 = st.columns(2)

# --- PLOT 1: Benutzergruppe ---
with c1:
    st.subheader("Benutzergruppe")
    if group_col in df_filtered.columns:
        data_grp = df_filtered[group_col].fillna("Unbekannt").value_counts().reset_index()
        data_grp.columns = ["Gruppe", "Anzahl"]
        data_grp = data_grp.sort_values(by="Anzahl", ascending=False)
        
        total_gruppen = len(data_grp)
        data_grp_top10 = data_grp.head(10)
        data_grp_chart = data_grp_top10.iloc[::-1].reset_index(drop=True)
        
        st.caption(f"Top 10 von {total_gruppen}")
        
        if not data_grp_chart.empty:
            max_val_grp = data_grp_top10["Anzahl"].max()
            data_grp_chart['color_log'] = np.log10(data_grp_chart['Anzahl'] + 1)

            fig = px.bar(
                data_grp_chart, y="Gruppe", x="Anzahl", color="color_log", 
                color_continuous_scale="Greens", orientation="h", height=300, 
                range_color=[np.log10(1), np.log10(max_val_grp + 1)]
            )
            fig.update_layout(showlegend=False, margin={"t": 10, "b": 0, "l": 100, "r": 10}, xaxis_title="Anzahl")
            fig.update_coloraxes(colorbar=dict(title="Anzahl", tickvals=[np.log10(1), np.log10(10), np.log10(100)], ticktext=["1", "10", "100"], thickness=10))
            st.plotly_chart(fig, use_container_width=True)
            
            # Expander für Tabelle
            with st.expander("Alle Gruppen anzeigen"):
                st.dataframe(data_grp, hide_index=True, use_container_width=True)
    else:
        st.caption("Keine Daten verfügbar.")

# --- PLOT 2: Wohnort ---
with c2:
    st.subheader("Wohnort")
    col_gemeinde = 'Ort_Norm' if 'Ort_Norm' in df_filtered.columns else ('Ort_Validiert' if 'Ort_Validiert' in df_filtered.columns else None)

    if col_gemeinde and df_filtered[col_gemeinde].notna().any():
        data_gm = df_filtered[col_gemeinde].fillna("Unbekannt").value_counts().reset_index()
        data_gm.columns = ["Gemeinde", "Anzahl"]
        data_gm = data_gm.sort_values(by="Anzahl", ascending=False)
        
        total_gemeinden = len(data_gm)
        data_gm_top10 = data_gm.head(10)
        data_gm_chart = data_gm_top10.iloc[::-1].reset_index(drop=True)
        
        st.caption(f"Top 10 von {total_gemeinden}")
        
        if not data_gm_chart.empty:
            max_val = data_gm_top10["Anzahl"].max()
            data_gm_chart['color_log'] = np.log10(data_gm_chart['Anzahl'] + 1)
            
            fig = px.bar(
                data_gm_chart, y="Gemeinde", x="Anzahl", color="color_log", 
                color_continuous_scale="Blues", orientation="h", height=300,
                range_color=[np.log10(1), np.log10(max_val + 1)]
            )
            fig.update_layout(showlegend=False, margin={"t": 10, "b": 0, "l": 100, "r": 10}, xaxis_title="Anzahl")
            fig.update_coloraxes(colorbar=dict(title="Anzahl", tickvals=[np.log10(1), np.log10(10), np.log10(100)], ticktext=["1", "10", "100"]))
            st.plotly_chart(fig, use_container_width=True)
            
            # Expander für Tabelle
            with st.expander("Alle Gemeinden anzeigen"):
                st.dataframe(data_gm, hide_index=True, use_container_width=True)
    else:
        st.caption("Keine Daten verfügbar.")

# Zeile 2: Altersverteilung & Geschlecht
c3, c4 = st.columns(2)

# --- PLOT 3: Altersverteilung (Mit logarithmischer Farbskala) ---
with c3:
    st.subheader("Altersverteilung")
    
    if "Geburtsdatum" in df_filtered.columns:
        df_age = df_filtered.copy()
        df_age['Geburtsdatum_DT'] = pd.to_datetime(df_age['Geburtsdatum'], format='%m/%d/%Y', errors='coerce')
        count_invalid = df_age['Geburtsdatum_DT'].isna().sum()
        
        today = pd.Timestamp.now()
        df_age['Alter'] = (today - df_age['Geburtsdatum_DT']).dt.days // 365
        df_age_plot = df_age[(df_age['Alter'] >= 0) & (df_age['Alter'] <= 110)]
        
        if count_invalid > 0:
            st.caption(f"Basis: {len(df_age_plot):,} Pers. ({count_invalid:,} ohne Datum ignoriert)")
        else:
            st.caption(f"Basis: {len(df_age_plot):,} Personen")

        if not df_age_plot.empty:
            # 1. Histogramm-Daten berechnen
            bins = np.linspace(0, 100, 21) # 20 Bins
            counts, bin_edges = np.histogram(df_age_plot['Alter'], bins=bins)
            
            df_plot = pd.DataFrame({
                'Alter_Start': bin_edges[:-1],
                'Alter_End': bin_edges[1:],
                'Anzahl': counts
            })
            
            # 2. Logarithmische Farbe vorbereiten
            # Wir erstellen eine Hilfsspalte für die Farbe: log10(Anzahl + 1)
            # "+1" verhindert log(0) und sorgt dafür, dass 0 -> 0, 1 -> 0.3, 9 -> 1, 99 -> 2
            df_plot['color_log'] = np.log10(df_plot['Anzahl'] + 1)
            
            max_log_val = df_plot['color_log'].max()
            min_log_val = 0 # log10(0+1) = 0
            
            # 3. Plot erstellen
            # Wir färben nach der Spalte 'color_log', beschriften die Achse aber manuell
            fig = px.bar(
                df_plot, 
                x="Alter_Start", 
                y="Anzahl", 
                color="color_log", # Farbe basiert auf Log-Wert
                color_continuous_scale="Purples",
                range_color=[min_log_val, max_log_val],
                opacity=0.9, 
                title=""
            )
            
            # 4. Layout & Achsen
            fig.update_layout(
                margin={"t": 10, "b": 0, "l": 10, "r": 10},
                xaxis_title="Alter (Jahre)", 
                yaxis_title="Anzahl Personen",
                height=300, 
                showlegend=False, 
                bargap=0.1
            )
            fig.update_xaxes(range=[0, 100], tickmode='linear', dtick=10)
            
            # 5. Farbleiste anpassen (Die Trickserei für die Beschriftung)
            # Wir überschreiben die Tick-Werte der Farbleiste, damit sie wieder die echten Zahlen (1, 10, 100) anzeigt
            # statt der Log-Werte (0, 1, 2).
            fig.update_coloraxes(
                colorbar=dict(
                    title="Anzahl (log)", 
                    thickness=10,
                    tickvals=[0, np.log10(10+1), np.log10(100+1)], # Ungefähre Positionen für 1, 10, 100
                    ticktext=["1", "10", "100+"],
                    outlinecolor="rgba(0,0,0,0)"
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Expander für Tabelle
            with st.expander("Altersgruppen-Daten anzeigen"):
                df_table = df_plot[df_plot['Anzahl'] > 0].copy()
                df_table['Alter_Bereich'] = df_table.apply(lambda r: f"{int(r['Alter_Start'])} - {int(r['Alter_End'])}", axis=1)
                st.dataframe(df_table[['Alter_Bereich', 'Anzahl']], hide_index=True, use_container_width=True)

        else:
            st.warning("Keine plausiblen Altersdaten gefunden.")
    else:
        st.caption("Spalte 'Geburtsdatum' nicht vorhanden.")

# --- PLOT 4: Geschlechterverteilung (Angepasste Farben) ---
with c4:
    st.subheader("Geschlechterverteilung")
    
    if "Anrede" in df_filtered.columns:
        df_gender = df_filtered.copy()
        
        def clean_gender(val):
            if pd.isna(val): return "Unbekannt"
            val_str = str(val).strip()
            if val_str == "Herr": return "Männlich"
            if val_str == "Frau": return "Weiblich"
            return "Andere"
            
        df_gender['Geschlecht_Bereinigt'] = df_gender['Anrede'].apply(clean_gender)
        
        data_gender = df_gender['Geschlecht_Bereinigt'].value_counts().reset_index()
        data_gender.columns = ["Geschlecht", "Anzahl"]
        
        order = ["Weiblich", "Männlich", "Andere", "Unbekannt"]
        data_gender['sort_order'] = data_gender['Geschlecht'].apply(lambda x: order.index(x) if x in order else 99)
        data_gender = data_gender.sort_values('sort_order')
        
        total_gender = len(df_filtered)
        count_unknown = data_gender[data_gender['Geschlecht'].isin(["Andere", "Unbekannt"])]['Anzahl'].sum()
        
        st.caption(f"Basis: {total_gender:,} Personen ({count_unknown:,} ohne klare Anrede)")

        if not data_gender.empty:
            # Angepasste, harmonische Farbpalette
            fig = px.pie(
                data_gender,
                values="Anzahl",
                names="Geschlecht",
                color="Geschlecht",
                color_discrete_map={
                    "Weiblich": "#D66D75",    # Gedecktes Rosenholz / Terra (wirkt erwachsen & warm)
                    "Männlich": "#5D8AA8",    # Luftiges Schieferblau (passt zu den blauen Plots)
                    "Andere": "#B0B0B0",  # Mittleres Grau
                    "Unbekannt": "#E0E0E0" # Helles Grau
                },
                hole=0.4,
                height=300
            )
            
            fig.update_traces(
                textposition='inside', 
                textinfo='percent+label', 
                textfont_size=12,
                textfont_color="#ffffff", # Weisse Schrift für besseren Kontrast auf den dunkleren Tönen
                marker=dict(line=dict(color='#ffffff', width=2))
            )
            
            fig.update_layout(
                margin={"t": 10, "b": 0, "l": 0, "r": 0}, 
                showlegend=False, 
                uniformtext_minsize=10, 
                uniformtext_mode='hide'
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("Absolute Zahlen anzeigen"):
                st.dataframe(data_gender[["Geschlecht", "Anzahl"]], hide_index=True, use_container_width=True)
                
    else:
        st.caption("Spalte 'Anrede' nicht vorhanden.")

# ==============================================================================
# 3. VORBEREITUNG DATENQUALITÄT (Für die Karte benötigt)
# ==============================================================================
# Wir berechnen hier die Masken UND df_complete, damit die Karte darauf zugreifen kann.

STATUS_OK = '✅ OK'
STATUS_CORRECTED_LIST = ['⚠️ Korrigiert', '⚠️ Ort korrigiert', '⚠️ PLZ korrigiert']
STATUS_UNKNOWN = '❌ Unbekannt'

# 1. Unvollständige Daten identifizieren
mask_incomplete = (
    df_filtered['PLZ'].isna() | 
    (df_filtered['PLZ'].astype(str).str.strip() == '') | 
    (df_filtered['PLZ'].astype(str).str.lower() == 'nan') |
    df_filtered['Wohnort'].isna() | 
    (df_filtered['Wohnort'].astype(str).str.strip() == '') |
    (df_filtered['Wohnort'].astype(str).str.lower() == 'nan')
)

# 2. Nur vollständige Daten für die weitere Analyse nutzen
df_complete = df_filtered[~mask_incomplete].copy()

# 3. Status-Masken erstellen (nur auf vollständigen Daten)
# Falls die Spalte 'Ort_Match_Status' noch nicht existiert (Fallback), erstellen wir sie temporär
if 'Ort_Match_Status' not in df_complete.columns:
    # Fallback: Alle als unbekannt markieren, wenn Validierung fehlgeschlagen ist
    df_complete['Ort_Match_Status'] = '❌ Unbekannt'
    # Oder als OK, wenn Ort_Validiert existiert:
    if 'Ort_Validiert' in df_complete.columns:
        df_complete['Ort_Match_Status'] = '✅ OK'

mask_ok = df_complete['Ort_Match_Status'] == STATUS_OK
mask_corrected = df_complete['Ort_Match_Status'].isin(STATUS_CORRECTED_LIST)
mask_unknown = df_complete['Ort_Match_Status'] == STATUS_UNKNOWN

# ==============================================================================
# 4. KARTE DER NUTZER:INNEN
# ==============================================================================
st.divider()
st.subheader("🗺️ NutzerInnen nach Wohngemeinde")

# ... (Der Rest des Codes für Referenzdaten und Shapefile bleibt gleich wie unten) ...
# 1. Referenzdaten für Hauptgemeinde-Logik laden
ref_csv_path = Path("data/swiss_locations.csv")
if not ref_csv_path.exists():
    st.error("Referenzdatei nicht gefunden!")
    st.stop()

try:
    df_ref_official = pd.read_csv(ref_csv_path, sep=';', dtype=str)
    df_ref_official['Adressenanteil_Num'] = df_ref_official['Adressenanteil'].str.replace('%', '').str.replace(',', '.').astype(float)
    
    idx_max_plz = df_ref_official.groupby('PLZ4')['Adressenanteil_Num'].idxmax()
    df_ref_plz_clean = df_ref_official.loc[idx_max_plz].copy()
    
    idx_max_name = df_ref_official.groupby('Ortschaftsname')['Adressenanteil_Num'].idxmax()
    df_ref_name_clean = df_ref_official.loc[idx_max_name].copy()
    
    df_ref_name_clean['BFS-Nr_Str'] = df_ref_name_clean['BFS-Nr'].astype(str).str.zfill(4)
    ort_to_bfs = pd.Series(df_ref_name_clean['BFS-Nr_Str'].values, index=df_ref_name_clean['Ortschaftsname']).to_dict()
    
    df_ref_plz_clean['BFS-Nr_Str'] = df_ref_plz_clean['BFS-Nr'].astype(str).str.zfill(4)
    df_ref_plz_clean['PLZ4_Str'] = df_ref_plz_clean['PLZ4'].astype(str).str.zfill(4)
    
    plz_counts = df_ref_plz_clean.groupby('PLZ4_Str')['BFS-Nr_Str'].nunique()
    ambiguous_plzs = plz_counts[plz_counts > 1].index.tolist()
    unique_plz_map = pd.Series(
        df_ref_plz_clean[~df_ref_plz_clean['PLZ4_Str'].isin(ambiguous_plzs)]['BFS-Nr_Str'].values, 
        index=df_ref_plz_clean[~df_ref_plz_clean['PLZ4_Str'].isin(ambiguous_plzs)]['PLZ4_Str']
    ).to_dict()

except Exception as e:
    st.error(f"Fehler beim Laden der Referenz: {e}")
    st.stop()

# 2. Shapefile laden
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
    bfs_col_shp = 'BFS_NUMMER'
    name_col = 'NAME'
    
    if bfs_col_shp not in gdf.columns:
        st.error(f"Spalte {bfs_col_shp} nicht im Shapefile gefunden!")
        st.stop()

    gdf_clean = gdf[[bfs_col_shp, name_col, 'geometry']].copy()
    gdf_clean.rename(columns={bfs_col_shp: 'bfs_nr', name_col: 'gemeinde_name'}, inplace=True)
    gdf_clean['bfs_nr'] = gdf_clean['bfs_nr'].astype(str).str.zfill(4)
    gdf_clean = gdf_clean.drop_duplicates(subset=['bfs_nr'])
    
    if gdf_clean.crs.to_epsg() != 4326:
        gdf_clean = gdf_clean.to_crs("EPSG:4326")

    # 3. Nutzerdaten zuordnen
    # HIER IST DER FIX: df_complete wurde oben in Sektion 3 definiert!
    df_map = df_complete[mask_ok | mask_corrected].copy()
    
    lookup_col = 'Ort_Norm' if 'Ort_Norm' in df_map.columns else 'Ort_Validiert'
    
    if lookup_col not in df_map.columns:
        st.error("Keine gültige Ort-Spalte gefunden.")
        st.stop()

    df_map['ort_lookup'] = df_map[lookup_col].astype(str).str.strip()
    df_map['plz_clean'] = df_map['PLZ'].astype(str).str.extract('(\d{4})')[0]

    df_map['bfs_nr'] = df_map['ort_lookup'].map(ort_to_bfs)
    mask_missing = df_map['bfs_nr'].isna() & df_map['plz_clean'].notna()
    
    if mask_missing.any():
        df_map.loc[mask_missing, 'bfs_nr'] = df_map.loc[mask_missing, 'plz_clean'].map(unique_plz_map)

    df_valid = df_map[df_map['bfs_nr'].notna()]
    
    if df_valid.empty:
        st.warning("Keine Daten für die Karte verfügbar.")
    else:
        # 1. Basis-Aggregation (Anzahl pro Gemeinde)
        user_counts = df_valid.groupby('bfs_nr').size().reset_index(name='Anzahl_Kunden')
        
        # 2. NEU: Aggregation der Benutzergruppen pro Gemeinde
        # Wir gruppieren nach bfs_nr und Benutzergruppe und zählen
        gruppen_counts = df_valid.groupby(['bfs_nr', group_col]).size().reset_index(name='count')
        
        # Wir formatieren das als String: "Erwachsene: 50, Kinder: 20, ..."
        # Dazu gruppieren wir wieder nach bfs_nr und fassen die Strings zusammen
        def format_gruppen(row):
            # row ist ein DataFrame mit den Gruppen dieser einen Gemeinde
            items = [f"{r[group_col]}: {r['count']}" for _, r in row.iterrows()]
            return "<br>".join(items) # <br> sorgt für Zeilenumbruch im Tooltip

        gruppen_info = gruppen_counts.groupby('bfs_nr').apply(format_gruppen).reset_index()
        gruppen_info.columns = ['bfs_nr', 'Gruppen_Detail']
        
        # 3. Zusammenführen der Aggregationen
        user_counts = user_counts.merge(gruppen_info, on='bfs_nr', how='left')
        
        user_counts['bfs_nr'] = user_counts['bfs_nr'].astype(str)
        
        merged_gdf = gdf_clean.merge(user_counts, on='bfs_nr', how='inner')
        
        if merged_gdf.empty:
            st.error("Keine Übereinstimmung mit dem Shapefile gefunden.")
        else:
            geojson_data = merged_gdf.__geo_interface__
            for i, feature in enumerate(geojson_data['features']):
                feature['properties']['bfs_nr'] = str(merged_gdf.iloc[i]['bfs_nr'])

            top_gemeinde = merged_gdf.loc[merged_gdf['Anzahl_Kunden'].idxmax()]
            centroid = top_gemeinde.geometry.centroid
            top_count = top_gemeinde['Anzahl_Kunden']
            
            if top_count > 1000: dynamic_zoom = 8
            elif top_count > 100: dynamic_zoom = 9
            else: dynamic_zoom = 10

            merged_gdf['color_log'] = np.log10(merged_gdf['Anzahl_Kunden'] + 1)

            fig = px.choropleth_mapbox(
                merged_gdf,
                geojson=geojson_data,
                locations="bfs_nr",
                featureidkey="properties.bfs_nr",
                color="color_log", 
                color_continuous_scale="YlGnBu",
                mapbox_style="carto-positron",
                zoom=dynamic_zoom,
                center={"lat": centroid.y, "lon": centroid.x},
                opacity=0.8,
                #title=f"Fokus: {top_gemeinde['gemeinde_name']}",
                hover_name="gemeinde_name",
                # HIER DIE ÄNDERUNG:
                hover_data={
                    "Anzahl_Kunden": True,       # Zeige Gesamtzahl
                    "Gruppen_Detail": True,      # Zeige die detaillierte Liste der Gruppen
                    "color_log": False,          # Verstecke den Log-Wert
                    "bfs_nr": False              # Verstecke die BFS-Nr
                }
            )
            
            # Optional: Tooltip etwas schöner formatieren (Schriftgröße)
            fig.update_traces(
                hovertemplate="<b>%{hovertext}</b><br>" +
                              "Total: %{customdata[0]}<br>" +
                              "%{customdata[1]}<extra></extra>"
            )
            # Hinweis: hovertemplate ist manchmal nötig, wenn hover_data nicht perfekt formatiert wird.
            # Aber oft reicht das obige hover_data Argument völlig aus.
            # Wenn die Gruppen einfach nur untereinander stehen sollen, ist hover_data={'Gruppen_Detail': True} meist genug.

            fig.update_layout(
                coloraxis_colorbar=dict(
                    title="Anzahl Nutzende",
                    tickvals=[np.log10(1), np.log10(10), np.log10(100), np.log10(1000)],
                    ticktext=["1", "10", "100", "1'000"]
                ),
                margin={"r":0, "t":50, "l":0, "b":0}, 
                height=600
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption("💡 Die Karte ist logarithmisch skaliert. Hover über eine Gemeinde, um die Verteilung nach Benutzergruppen zu sehen.")

except Exception as e:
    st.error(f"Fehler bei der Kartenerstellung: {e}")
    st.code(str(e))


# ==============================================================================
# 6. DATENQUALITÄT
# ==============================================================================

st.subheader("Datenqualität")

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

# Details zur Datenqualität (Einblendbar)
if count_unknown > 0 or count_incomplete > 0 or count_corr > 0:
    with st.expander("📋 Details zur Datenqualität anzeigen"):
        tabs = []
        if count_unknown > 0: tabs.append("❌ Fehlerhafte Orte")
        if count_incomplete > 0: tabs.append("⚪ Fehlende Daten")
        if count_corr > 0: tabs.append("🛠️ Autom. Korrekturen")
        
        if tabs:
            panes = st.tabs(tabs)
            idx = 0
            
            if count_unknown > 0:
                with panes[idx]:
                    st.warning(f"**{count_unknown}** Datensätze haben eine ungültige PLZ/Ort-Kombination.")
                    df_problems = df_complete[mask_unknown]
                    df_problems['Kombi'] = df_problems['PLZ'].astype(str) + " | " + df_problems['Wohnort'].astype(str)
                    top_errors = df_problems['Kombi'].value_counts().head(10).reset_index()
                    top_errors.columns = ["Eingegebene Kombination", "Anzahl"]
                    st.dataframe(top_errors, hide_index=True, use_container_width=True)
                    st.info("💡 **Ursache:** Tippfehler oder Ausland. Bitte in BiThek korrigieren.")
                idx += 1

            if count_incomplete > 0:
                with panes[idx]:
                    st.info(f"**{count_incomplete}** Datensätze haben keine PLZ oder keinen Wohnort.")
                    m_plz = df_filtered[mask_incomplete & (df_filtered['PLZ'].isna() | (df_filtered['PLZ'].astype(str).str.strip() == ''))].shape[0]
                    m_ort = df_filtered[mask_incomplete & (df_filtered['Wohnort'].isna() | (df_filtered['Wohnort'].astype(str).str.strip() == ''))].shape[0]
                    cm1, cm2 = st.columns(2)
                    cm1.metric("Davon ohne PLZ", m_plz)
                    cm2.metric("Davon ohne Wohnort", m_ort)
                    st.info("💡 **Ursache:** Oft Testaccounts oder unvollständige Registrierung.")
                    st.caption("Empfehlung: Stammdaten in BiThek nachpflegen.")
                idx += 1

            if count_corr > 0:
                with panes[idx]:
                    st.success(f"**{count_corr}** Einträge wurden automatisch bereinigt.")
                    df_corr = df_complete[mask_corrected][['PLZ', 'Wohnort', 'Ort_Validiert']].drop_duplicates().head(15)
                    st.dataframe(df_corr.rename(columns={"Wohnort": "Original", "Ort_Validiert": "Korrektur"}), hide_index=True, use_container_width=True)
                    st.caption("Empfehlung: Stammdaten in BiThek nachpflegen.")
else:
    st.divider()
    st.success("🎉 Perfekte Datenqualität! Alle Nutzer wurden erfolgreich zugeordnet.")