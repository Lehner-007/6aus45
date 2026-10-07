# Änderungen

## 0.2.4 — 07.10.2026

- Feste, nicht verschiebbare Spaltenbreiten in den Ergebnislisten; Auswertungswechsel verändert sie nicht.
- Joker-Auswertungen nur bei Joker anbieten, Lotto-Auswertungen nur bei Lotto.
- Statistik bei Spiel- und Auswertungswechsel sofort aktualisieren; Auswahlbeschriftung und Ergebnisse stimmen überein.

## 0.2.3 — 07.10.2026

- Quellenliste in Einstellungen auf Häkchen und Link reduziert; + zum Hinzufügen und − zum Entfernen.
- Vorhandene Importzuordnungen intern erhalten; neue Links ohne technische Auswahlfelder zuordnen.

## 0.2.2 — 07.10.2026

- Datumsspalte auf kompakte 125 logische Pixel verkleinert.
- Leere Spalten auf der angezeigten Ergebnis-Seite automatisch ausblenden und bei Inhalt wieder anzeigen, einschließlich Filtern und Spielwechsel. Numerische Null bleibt gültiger Inhalt.

## 0.2.1 — 07.10.2026

- Wasserzeichen auf fünf Prozent Deckkraft reduziert und im Programm auf höchstens 300 × 300 Pixel begrenzt.
- Zahlen- und Zusatzzahlspalte kompakt auf sechs beziehungsweise eine Kugel abgestimmt.
- Grüne Zusatzzahl in der Tabelle nur in der eigenen Zusatzzahlspalte; die Zahlenspalte enthält sechs Hauptzahlen.

## 0.2.0 — 07.10.2026

- Vereinbartes Wolf-und-D-Wasserzeichen unabhängig vom Programmlogo in Anwendung, Hilfe und HTML-Berichten.
- Blaue Jokerziffern und Kugelbilder direkt in Ziehungs- und Tipplisten; automatische Vorschau nach Tipp-Erstellung.
- Quotenimport aus Lottoarchiven, Joker-PDF/CSV und amtlichem Ergebnisdienst. ATS/EUR, Jackpot-Pool, Gewinnerzahl und fehlender Betrag bleiben getrennt.
- Ziehungsquellen in Einstellungen anzeigen, hinzufügen, bearbeiten, entfernen und aktivieren; Speichern/Abbrechen berücksichtigen. Auch CLI-Update verwendet die Auswahl.
- Alte und aktuelle 6aus45-Datenbanken lesend importieren. Von Josef bestätigte archivierte Historie mit Herkunft übernommen; gleiche Bestände nicht doppelt importieren.
- SQLite-Schema 2 mit automatischer vorheriger Sicherung und Erhaltung persönlicher Daten.

## 0.1.0

Erste Umsetzung mit vollständigem Lotto-/Joker-Grundbestand, realen Ziehungen, Statistik, Tipp-Erstellung, Import und gemeinsamen GUI-Bausteinen.
