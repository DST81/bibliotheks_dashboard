# Praktikumsbericht - Projektzusammenfassung Dashboard V1.0

Stand: 20. August 2026

## 1. Projektidee

Im Praktikum wurde ein interaktives Bibliotheks-Dashboard entwickelt. Ziel war es, Daten aus dem Bibliothekssystem BiThek/FileMaker so aufzubereiten, dass sie für Leitung, Bestandsarbeit und operative Auswertungen verständlich und nutzbar werden.

Das Dashboard richtet sich an Bibliotheken, die ihre Ausleihen, Benutzenden, Medienbestände, Neuanschaffungen und OpenLibrary-Zutritte nicht nur als Rohdaten, sondern als Kennzahlen, Diagramme und filterbare Analysen betrachten möchten.

Der Schwerpunkt von Version 1.0 liegt auf einer funktionierenden, praxisnahen Auswertungsplattform:

- zentrale Startseite mit Leitungskennzahlen
- Detailseiten für Ausleihen, Benutzende, Medien, Top-Medien, Bestand und OpenLibrary
- einheitliche Filterlogik
- robuste Datenladung aus zwischengespeicherten FileMaker-Exports
- erste PDF-Berichte
- Mehrbibliotheksfähigkeit über getrennte Datenkontexte
- visuell vereinheitlichte Farbwelt

## 2. Ausgangslage und Motivation

Viele Daten liegen im Bibliothekssystem zwar vor, sind aber im Alltag nur schwer übergreifend auswertbar. Einzelne Fragestellungen benötigen oft manuelle Exporte, Tabellenbereinigung oder wiederholte Berechnungen.

Das Dashboard soll diese Arbeit vereinfachen. Wiederkehrende Fragen können direkt beantwortet werden, zum Beispiel:

- Wie entwickeln sich die Ausleihen im Vergleich zum Vorjahr?
- Welche Medienarten oder Standorte werden stark genutzt?
- Welche Benutzergruppen sind besonders aktiv?
- Welche Medien wurden häufig oder gar nicht ausgeliehen?
- Welche Bestandsbereiche sollten überprüft oder bereinigt werden?
- Wie wird OpenLibrary genutzt?
- Welche Wirkung haben Ferienzeiten oder Öffnungszeiten auf Zutritte und Ausleihen?

## 3. Technische Grundlage

Das Projekt ist als Streamlit-App in Python umgesetzt.

Wichtige Bibliotheken:

- `streamlit` für die Weboberfläche
- `pandas` und `numpy` für Datenverarbeitung
- `altair` und `plotly` für Diagramme
- `geopandas` für geografische Benutzeranalysen
- `fpdf2` für PDF-Export
- `python-dotenv` für Umgebungsvariablen
- `requests` für FileMaker-Zugriffe

Die zentrale App-Datei ist `Home.py`. Weitere Analysebereiche liegen im Ordner `pages/`.

## 4. Projektstruktur

```text
Home.py                         Startseite und Leitungsdashboard
pages/01_Ausleihen.py           Ausleihanalysen und Zielgruppenvergleiche
pages/02_Benutzer.py            Benutzeranalyse und Ortsvalidierung
pages/03_Medien.py              Neuanschaffungen und Beschaffungskosten
pages/03_Top_Medien.py          Top-Medien und PDF-Toplisten
pages/04_Bestand.py             Bestandsanalyse und Bereinigungsscores
pages/05_OpenLibrary.py         OpenLibrary-Zutritte und Ausleihen
pages/10_Settings.py            Einstellungen für Ferien und OpenLibrary
components/ui.py                Wiederverwendbare KPI- und Detailkomponenten
components/icons.py             Zentrale Icon-Pfade
src/filters.py                  Zentrale Sidebar-Filterlogik
src/utils.py                    Datenladen, Mandantenkontext, Hilfsfunktionen
src/theme.py                    Zentrale Farben und Design-Tokens
src/pdf_report.py               PDF-Erstellung
src/report_helpers.py           Hilfsfunktionen für Berichte
src/bestand_analysis.py         Bestands- und Bereinigungslogik
scripts/fetch_all_data.py       Datenabruf aus FileMaker
```

## 5. Datenquellen und Datenfluss

Die App arbeitet mit JSON-Caches, die aus FileMaker exportiert oder über das Fetch-Script aktualisiert werden.

Erwartete Datenquellen:

- Ausleihen
- Katalog
- Antiquariat
- Benutzende
- OpenLibrary-/SmartLibrary-Protokolle

Typische Cache-Dateien:

```text
Ausleihe_Liste_YYYY-MM-DD.json
Katalogisieren_YYYY-MM-DD.json
Antiquariat_YYYY-MM-DD.json
Benutzer_Dashboard_YYYY-MM-DD.json
SmartLibraryProtokoll_YYYY-MM-DD.json
```

Die App lädt jeweils die neueste passende Datei. Wenn einzelne Datenquellen fehlen, soll die App möglichst robust reagieren und eine verständliche Meldung anzeigen.

Der Datenfluss:

1. Daten werden aus FileMaker geholt oder aus dem lokalen Cache geladen.
2. Die Daten werden normalisiert, bereinigt und zeitlich interpretiert.
3. Sidebar-Filter werden angewendet.
4. Katalog-, Benutzer- und Ausleihdaten werden je nach Seite zusammengeführt.
5. Kennzahlen, Tabellen, Diagramme und PDF-Berichte werden daraus erzeugt.

## 6. Mehrbibliotheksfähigkeit

Das Dashboard ist für mehrere Bibliotheken vorbereitet. Jede Bibliothek kann einen eigenen Datenordner und einen eigenen Zugriffsschlüssel verwenden.

Wichtige Konzepte:

- Bibliothekskontext über `get_library_context()`
- getrennte Cache-Verzeichnisse unter `data/libraries/<bibliothek_id>/cache`
- Zugriffsschutz über `access_key`
- bibliotheksspezifische FileMaker-Umgebungsvariablen

Dadurch kann dieselbe App grundsätzlich für mehrere Bibliotheken verwendet werden, ohne die Daten zu vermischen.

## 7. Zentrale Filterlogik

Ein wichtiger Teil des Projekts ist die zentrale Filterlogik in `src/filters.py`.

Die Seiten verwenden vor allem:

```python
get_sidebar_filters(...)
build_filtered_data(...)
```

Damit können Benutzer-, Ausleih- und Katalogfilter einheitlich angewendet werden.

Wichtige Filterbereiche:

- Benutzergruppe
- Geschlecht
- Alter
- Wohnort
- Self-Service/OpenLibrary-Kategorie
- Ausleihzeitraum
- Zweigstelle
- Medienart
- Lesealter
- Standort
- Themenbereich
- Signatur
- Neuanschaffungszeitraum
- Preisbereich

Ein wichtiges Konzept ist `loans_no_date`: Diese Daten behalten alle nichtzeitlichen Filter, ignorieren aber den Datumsfilter. Das ist wichtig für Vergleiche mit Vorjahren, Bestandsberechnungen oder Jahreskennzahlen.

## 8. Startseite / Leitungsdashboard

Die Startseite `Home.py` dient als Überblick für die Bibliotheksleitung.

Umgesetzte Funktionen:

- Datenstatus und letzte Aktualisierung
- Button zum Aktualisieren der Daten aus FileMaker
- zentrale Jahreskennzahlen
- Vergleich aktuelles Jahr vs. Vorjahr
- Ausleihtrend mit App/Theke-Unterscheidung
- kumulierte Ausleihen im Jahresvergleich
- OpenLibrary-Arbeitslast seit letzter bedienter Öffnungszeit
- PDF-Export für einen kompakten Leitungsbericht

Besonders wichtig ist der OpenLibrary-Abschnitt auf der Startseite. Er zeigt:

- App-Ausleihen seit letzter bedienter Öffnungszeit
- App-Rückgaben seit letzter bedienter Öffnungszeit
- Zutritte seit letzter bedienter Öffnungszeit
- Ausleihen pro Zutritt
- Rückgaben pro Zutritt
- Zutritte pro Tag
- erkannte Zweigstellen

Damit lässt sich einschätzen, welche Nutzung während unbedienter Zeiten entstanden ist.

## 9. Ausleihen-Analyse

Die Seite `pages/01_Ausleihen.py` zeigt detaillierte Auswertungen der Ausleihen.

Umgesetzte Funktionen:

- Zeitverlauf der Ausleihen
- Ausleihen nach Medienart
- Ausleihen nach Standort
- Ausleihen nach Wochentag
- Wochentage im Jahresvergleich
- Zielgruppenvergleich nach Benutzergruppe oder Altersgruppen
- durchschnittliche Ausleihen pro Besuch
- durchschnittliche Besuche im Zeitraum
- Bestandsnutzung im gefilterten Bestand
- Ausleihen, Umsatz und Effizienz nach Medienart
- Ausleihen, Umsatz und Effizienz nach Standort

Die Diagramme wurden visuell an die zentrale Farbpalette angepasst.

## 10. Benutzeranalyse

Die Seite `pages/02_Benutzer.py` analysiert die Benutzenden.

Umgesetzte Funktionen:

- Benutzerkennzahlen
- Zielgruppenanalysen
- Geschlechterverteilung
- Alters- und Gruppenauswertungen
- Ortsvalidierung mit Schweizer Ortsdaten
- geografische Auswertungen
- Datenqualitätsprüfung

Ein wichtiger Bestandteil ist die Bereinigung und Validierung von Wohnorten, damit geografische Analysen zuverlässiger werden.

## 11. Medien und Neuanschaffungen

Die Seite `pages/03_Medien.py` untersucht Neuanschaffungen und Beschaffungskosten.

Umgesetzte Funktionen:

- Analyse neuer Medien
- Auswertung nach Lieferant
- Preis- und Kostenkennzahlen
- Ausleihnutzung von Neuanschaffungen
- Jahresvergleich
- Filter nach Preis, Neuanschaffungsdatum, Sprache, Medienart, Lesealter, Standort, Themenbereich und Signatur
- PDF-Bericht für Medienauswertungen

Die Seite unterstützt die Frage, wie gut neu angeschaffte Medien tatsächlich genutzt werden.

## 12. Top-Medien

Die Seite `pages/03_Top_Medien.py` zeigt die meist ausgeliehenen Medien.

Umgesetzte Funktionen:

- Auswahl der Anzahl Top-Medien
- Option, Medien ohne Ausleihe einzubeziehen
- Darstellung als Karten mit Cover, Titel, Autor, Reihe und Ausleihzahl
- PDF-Export der Top-Liste
- robuste Behandlung fehlender Spalten oder leerer Daten

Diese Seite eignet sich für schnelle Auswertungen, Empfehlungslisten oder interne Bestandsbeobachtung.

## 13. Bestandsanalyse

Die Seite `pages/04_Bestand.py` unterstützt die Bestandsarbeit.

Umgesetzte Funktionen:

- Kennzahlen zum gefilterten Bestand
- Bereinigungsscore
- Einteilung in `behalten`, `prüfen` und `Bereinigung prüfen`
- Portfolioanalyse nach Alter und Nutzung
- Detailansicht einzelner Medien
- Reihenkontext und Reihenprüfung
- Filter nach Standort, Medienart, Lesealter, Themenbereich und Signatur

Ziel ist es, Medien sichtbar zu machen, die wenig genutzt, veraltet oder für eine Bestandsbereinigung relevant sein könnten.

## 14. OpenLibrary-Analyse

Die Seite `pages/05_OpenLibrary.py` analysiert OpenLibrary-Zutritte und die Ausleihen von OpenLibrary-Nutzenden.

Umgesetzte Funktionen:

- OpenLibrary-KPIs
- aktive und abgelaufene OpenLibrary-Abos
- Zutritte pro Zeitraum
- Besucherzahlen
- Zutritte pro Besucher
- Durchschnitt pro Tag, Woche und Monat
- Kalenderwochenplot mit Zutritten, Ausleihen und Ferienbereichen
- Tagesverteilung einer ausgewählten Woche
- Stundenplots für Zutritte und Ausleihen
- Wochentagsplots für Zutritte und Ausleihen
- Ferien-/Saisonzeiten als konfigurierbare Markierungen

Die Legende und Farben wurden überarbeitet, damit klarer unterscheidbar ist:

- Ausleihen: Blau
- Zutritte: Türkis/Grün
- Ferien: farbige Hintergrundflächen
- Jahre: Linienmuster

## 15. Einstellungen

Die Seite `pages/10_Settings.py` dient zur Pflege von Einstellungen.

Umgesetzt:

- OpenLibrary-Zeitraum für Stundenplots
- Ferien und Saisonzeiten
- Ferienfarben
- Aktivieren und Deaktivieren einzelner Ferienbereiche

Die Einstellungen werden in `data/config.json` gespeichert.

## 16. Design und visuelle Vereinheitlichung

Für V1.0 wurde das Dashboard visuell vereinheitlicht.

Zentrale Datei:

```text
src/theme.py
```

Wichtige Farben:

- Hauptfarbe: `#2596be`
- Sekundärfarbe: `#2A9D8F`
- Akzentfarbe: `#E76F51`
- Erfolg: `#2E7D32`
- Warnung: `#F4A261`
- Gefahr: `#C62828`
- Text: `#263238`
- Rahmen: `#E5E7EB`

Die Hauptfarbe wurde an die SVG-Icons angepasst. Dadurch wirken Icons, Diagramme, KPI-Karten und Legenden stärker als zusammengehöriges Produkt.

Semantische Diagrammfarben:

- Ausleihen: `COLOR_LOANS`
- App-Kanal: `COLOR_APP`
- Rückgaben: `COLOR_RETURNS`
- Zutritte: `COLOR_VISITS`
- Vorjahr/Vergleich neutral: `COLOR_PREVIOUS`

## 17. PDF-Export

Für V1.0 gibt es erste PDF-Exporte:

- Leitungsbericht auf der Startseite
- Medien-/Neuanschaffungsbericht
- Top-Medien-Liste

Die PDF-Erzeugung liegt in `src/pdf_report.py`. Diagramme werden nach Möglichkeit als Bilder eingebettet. Wenn ein Diagramm nicht eingebettet werden kann, wird dies abgefangen und im Bericht vermerkt.

## 18. Robustheit und Fehlerbehandlung

Während der Entwicklung wurde darauf geachtet, dass die App möglichst nicht abstürzt, wenn Daten fehlen oder Spalten nicht vorhanden sind.

Beispiele:

- fehlende Datenquellen führen zu verständlichen Streamlit-Meldungen
- `None`-Daten werden auf leere DataFrames zurückgeführt
- fehlende Spalten werden geprüft
- Top-Medien-Seite stoppt sauber bei unvollständiger Datenbasis
- Datumswerte werden mit `errors="coerce"` robust geparst
- Medien-IDs werden für Joins normalisiert

## 19. Wichtige erreichte Ergebnisse in V1.0

- funktionsfähiges Streamlit-Dashboard
- zentrale Datenladung
- zentrale Filterlogik
- mehrere Analysebereiche
- Bestandsbewertung mit Bereinigungsscore
- OpenLibrary-Auswertungen
- PDF-Exporte
- Mehrbibliotheksfähigkeit vorbereitet
- visuell vereinheitlichte Farbpalette
- robustere Behandlung fehlender Daten
- klarere Legenden und semantische Diagrammfarben

## 20. Grenzen von V1.0

V1.0 ist funktional, aber noch nicht vollständig optimiert.

Bekannte Grenzen:

- einige Berechnungen sind noch direkt in den Seiten implementiert
- einzelne Seiten enthalten noch viel Code in einer Datei
- Performance kann bei sehr großen Datenmengen weiter optimiert werden
- visuelle Details sind noch nicht vollständig über ein Designsystem gekapselt
- automatisierte Tests sind erst begrenzt vorhanden
- PDF-Layout kann noch weiter professionalisiert werden
- einzelne Texte und Begriffe können noch redaktionell vereinheitlicht werden

## 21. Mögliche Optimierungen nach V1.0

Technische Optimierung:

- Berechnungslogik stärker in `src/` auslagern
- Seiten schlanker machen
- wiederverwendbare Chart-Funktionen erstellen
- mehr Tests für Filter, Joins und Kennzahlen
- Performance-Analyse mit großen Datenmengen
- Caching gezielter einsetzen
- PDF-Rendering stabilisieren und vereinheitlichen

Visuelle Optimierung:

- gemeinsame Chart-Helfer mit Standardfarben
- einheitliche Legenden-Komponenten
- einheitliche Seitenabstände und Überschriften
- bessere mobile Darstellung
- konsistente Icons und Seitentitel
- Farbkontrast und Barrierefreiheit prüfen

Inhaltliche Optimierung:

- Kennzahlendefinitionen dokumentieren
- Datenqualitätsindikatoren ergänzen
- mehr Vergleichslogik über mehrere Jahre
- Exportmöglichkeiten erweitern
- Benutzerführung auf den Analyse-Seiten verbessern

## 22. Mögliche Formulierungen für den Praktikumsbericht

### Kurzbeschreibung

Im Rahmen des Praktikums wurde ein interaktives Dashboard für Bibliotheksdaten entwickelt. Die Anwendung bereitet Daten aus BiThek/FileMaker auf und stellt sie als Kennzahlen, Diagramme und filterbare Analyseansichten dar. Ziel war es, wiederkehrende Auswertungen zu automatisieren und die Daten für Leitung, Bestandsarbeit und OpenLibrary-Auswertungen nutzbar zu machen.

### Technische Umsetzung

Die Anwendung wurde mit Python und Streamlit umgesetzt. Die Daten werden aus FileMaker-Exporten bzw. JSON-Caches geladen, mit Pandas bereinigt und über zentrale Filterfunktionen verarbeitet. Für Visualisierungen werden Altair und Plotly eingesetzt. Wiederverwendbare Komponenten wie KPI-Karten, Theme-Farben und PDF-Berichte wurden in eigene Module ausgelagert.

### Nutzen

Das Dashboard reduziert manuelle Auswertungsarbeit und macht Entwicklungen im Bibliotheksbetrieb schneller sichtbar. Es unterstützt die Beurteilung von Ausleihen, Bestandsnutzung, Benutzergruppen, Neuanschaffungen und OpenLibrary-Nutzung. Durch Filter und Vergleiche können einzelne Zielgruppen, Medienarten oder Standorte gezielt untersucht werden.

### Reflexion

Eine besondere Herausforderung bestand darin, heterogene Datenquellen miteinander zu verbinden und gleichzeitig robust mit fehlenden oder uneinheitlichen Daten umzugehen. Im Verlauf des Projekts wurde deshalb zunehmend Wert auf zentrale Filterlogik, normalisierte Schlüssel, klare Fehlerbehandlung und visuelle Vereinheitlichung gelegt. V1.0 bildet eine solide Grundlage, die in weiteren Schritten technisch optimiert und gestalterisch weiter vereinheitlicht werden kann.

## 23. Wichtige Dateien für die weitere Arbeit

- `README.md`: technische Projektbeschreibung
- `Home.py`: Leitungsdashboard und zentrale Startseite
- `src/theme.py`: Farben und visuelle Tokens
- `src/filters.py`: zentrale Filterlogik
- `src/utils.py`: Datenladung und Hilfsfunktionen
- `src/pdf_report.py`: PDF-Erstellung
- `pages/05_OpenLibrary.py`: komplexe OpenLibrary-Auswertung
- `pages/04_Bestand.py`: Bestands- und Bereinigungslogik

## 24. Möglicher Aufbau des fertigen Praktikumsberichts

1. Einleitung und Ausgangslage
2. Zielsetzung des Projekts
3. Verwendete Technologien
4. Datenquellen und Datenmodell
5. Umsetzung der zentralen Filterlogik
6. Beschreibung der einzelnen Dashboard-Seiten
7. Design und visuelle Vereinheitlichung
8. PDF-Export und Berichtsfunktionen
9. Herausforderungen und Lösungsansätze
10. Ergebnis von V1.0
11. Reflexion
12. Ausblick und mögliche Weiterentwicklung

