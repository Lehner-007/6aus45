# 6aus45 0.2.4

Lokale GTK-4-Anwendung für österreichisches Lotto 6 aus 45 und Joker. Arbeitsordner: `/home/josef/Labor/Python/6aus45`. Start: `./start.sh`. Keine Installation beim Start, keine Tippabgabe, keine Käufe.

## Voraussetzungen

System-Python ≥3.11, GTK 4/PyGObject, requests, Beautiful Soup, pdftotext (poppler-utils). Diese Komponenten sind in der verwendeten Labor-VM vorhanden. Keine Autorennamen ohne Vorgabe; `projekt.json` enthält eine anpassbare Autorenliste. GPL-3.0-only für den Programmcode; Logos und Kugelbilder wurden von Josef bereitgestellt. Offizielle Quelldaten sind mit Herkunft dokumentiert und fallen nicht automatisch unter die Programmlizenz.

## Ablage

- `6aus45.py`, `start.sh`: Einstieg und CLI.
- `modules/`: Fachlogik und eigenständige Kopie benötigter gemeinsamer Bausteine.
- `assets/`: Programmlogo, eigenes Wolf-und-D-Wasserzeichen, weiße/grüne Kugelbilder (1–45) und blaue Jokerziffern (0–9). Keine Abhängigkeit von Josefs Bilderordner zur Laufzeit.
- `lang/de.json`, `lang/en.json`, `help/de`, `help/en`: Oberfläche und Offline-Hilfe.
- `data/6aus45.sqlite`: gelieferter vollständiger Grundbestand und reale Historie.
- `sources/`: ausschließlich private Entwicklungsbelege: Originalarchive, übernommene Altdaten, URLs/Prüfsummen und Importberichte. Nicht in Benutzer-ZIP, DEB oder GitHub veröffentlichen. Die normale Anzeige liest aus SQLite und braucht diese Dateien nicht.
- `.config/`: private Entwicklungseinstellungen und rotierendes Protokoll. Keine öffentliche Auslieferung dieser persönlichen Daten.
- `tests/`: automatisierte Kern- und GTK-Prüfungen.

## Bedienung

F1 öffnet Hilfe → Hilfe. F5 aktualisiert die Anzeigen nach geänderten Statistikfiltern. Die Hilfe beschreibt alle Menüpunkte. Ein Klick auf eine Spaltenüberschrift sortiert die aktuelle Seite; große Bestände bleiben paginiert (100 Zeilen). Datum: dd.mm.yyyy. Die Spaltenbreiten sind fixiert und bleiben beim Wechsel der Auswertung gleich. Joker-Endungen stehen nur für Joker zur Auswahl. Spiel- und Auswertungswechsel aktualisieren die Statistik sofort. Die Datumsspalte ist kompakt. Leere Spalten werden auf der angezeigten Seite automatisch ausgeblendet; enthalten sie wieder Werte, werden sie sichtbar. Das gilt auch beim Spielwechsel und Filtern.

Tipp-Erstellung: Anzahl und optionalen reproduzierbaren Seed eingeben, über Auswertung → Tipps erstellen starten. Statistikregeln sind JSON und nur wirksam bei aktiviertem Statistikschalter. Beispiel:

```json
{"include":[1],"exclude":[45],"even":3,"sum_min":100,"sum_max":180,"neighbors_max":2}
```

`regions` enthält drei Anzahlen für 1–15, 16–30, 31–45 (Summe 6). `overlap_max` begrenzt gemeinsame Zahlen zwischen Tipps; die Suche ist begrenzt und verspricht keine maximal mögliche Seriengröße. `weight`: `frequent`, `rare`, `absent` ist eine weiche Gewichtung. Ohne Statistik werden diese Regeln vollständig ignoriert. Ausschlüsse gezogener und früher verwendeter Tipps sind unabhängig und standardmäßig aus.

Gleichverteilung ohne Regeln: alle Kombinationen werden bijektiv auf 1…8.145.060 abgebildet; `random.sample` wählt IDs ohne Zurücklegen. Jede zulässige ID hat dieselbe Chance. Mit harten Regeln wird der zulässige Bestand exakt bestimmt. Weiche Gewichte nutzen eine exponentielle Zufallsrangfolge ohne Zurücklegen. Keine Behauptung, dass diese Regeln die Gewinnchance erhöhen.

Die Ergebnistabellen zeigen die Lottozahlen als weiße Kugeln und Jokerziffern als blaue Kugeln, einschließlich führender Nullen. Neue Tipps werden sofort mit Bildern angezeigt; die erste Reihe erscheint zusätzlich als Vorschau bei der Tipp-Erstellung. Das Programmlogo bleibt vom Wolf-und-D-Wasserzeichen getrennt.

## CLI

```
./start.sh --help
./start.sh --version
./start.sh --author
./start.sh --verify
./start.sh --coverage
./start.sh --build
./start.sh --import-file sources/NN_W2D_STAT_Lotto_2026.csv
./start.sh --update
./start.sh --generate 10 --seed test
./start.sh --generate 100 --game joker --seed test
./start.sh --backup /gewünschter/pfad/sicherung.sqlite
```

`--db` wählt eine andere DB. Große Arbeiten sind im GUI kooperativ abbrechbar, fortsetzbare Grundbestands-Batches und teilweise gespeicherte Tippserien bleiben erhalten. SQLite-Backup-API statt bloßem Kopieren einer laufenden Datenbank.

## Austauschformat

JSON: Liste von Objekten oder `{"draws":[...]}`. Lotto: `game`, ISO-`date`, sechs Ganzzahlen unter `numbers`, `extra` (oder null). Joker: `game="joker"`, ISO-`date`, sechsstelliger Text unter `joker`. Optional `quotes` mit `rank`, `rule`, `winners`, `currency` (ATS/EUR), `amount` (Ganzzahl in Hundertsteln oder null), `kind` (per_winner/jackpot/unknown), `status`. Originale Quoten je Quellstand werden getrennt gespeichert. Optional `identity`, `time`, `official_id`, `draw_type` für tatsächlich belegte Ereignisidentitäten. Keine offiziellen IDs erfinden.

CSV mit Semikolon, UTF-8: `game;date;numbers;extra;joker;identity;time`; `numbers` enthält sechs kommagetrennte Zahlen. Joker führende Nullen bewahren. Die gleichbleibenden Kombinationen sind keine eindeutigen Ziehungsereignisse. Mehrere Ereignisse an einem Datum benötigen eine belegte zusätzliche Identität, sonst wird ein Ergebniswiderspruch als Konflikt behandelt.

Lokaler GUI-Import: Vorschau → ausdrücklich bestätigen. Konflikte werden gespeichert, nicht überschrieben. Eine geprüfte Korrektur braucht einen Grund und erzeugt einen Änderungsverlauf. Gewinnquoten werden importiert und unter der ausgewählten Ziehung angezeigt. ATS/EUR, Jackpot-Pool und Betrag je Gewinner bleiben getrennt. Fehlende Beträge erscheinen als Strich, nicht als null Euro. Abweichende Quotenquellen bleiben erhalten und werden gekennzeichnet. Keine finanzielle Tipp-Prognose oder Umrechnung historischer Beträge.

## Datenabdeckung und Quellen

Offizieller Einstieg Lotto: https://www.win2day.at/lotterie/lotto/lotto-statistik-zahlen-ergebnisse-download

Joker: https://www.win2day.at/lotterie/joker-statistik und https://www.win2day.at/lotterie/joker-ziehungen

`catalog.json` führt tatsächlich abgerufene URLs und SHA-256-Werte. Importiert: Lotto ab 07.09.1986 bis 04.10.2026, Joker ab 02.10.1988 bis 04.10.2026 einschließlich der von Josef als gültig bestätigten alten Datenbanken. Jahreszahlen und Anzahlen in `sources/coverage.json`. Die beiden alten 6aus45-Datenbanken enthalten denselben Bestand: 7.257 Ziehungen und 30.310 Quotenzeilen. Ihre Daten wurden einmal mit Herkunft übernommen; 3.130 Jokerziehungen kamen hinzu. Der aktuelle Bestand enthält 3.690 Lotto- und 3.581 Jokerziehungen; vorhandene persönliche Daten und Tippserien bleiben erhalten. Die Vollständigkeit aller historischen Sonderziehungen ist nicht unabhängig bewiesen. Aus Quellhinweisen wie der auf 01.01.1987 verschobenen Ziehung vom 28.12.1986 werden keine erfundenen Ergebnisse angelegt. LottoPlus ist nicht enthalten.

Datei → Einstellungen zeigt die drei vorbelegten Ziehungs-/Quotenquellen. Jede Zeile enthält nur Aktivierungshäkchen, Link und − zum Entfernen. + fügt einen Link hinzu. Benötigte Adapterangaben bleiben intern erhalten; neue Links werden anhand der Adresse beziehungsweise importierten Daten zugeordnet. Abbrechen verwirft Änderungen, Speichern übernimmt sie. Software- und Sprachquellen bleiben projektintern. Lokale alte oder aktuelle 6aus45-SQLite-Datenbanken können über Daten → Datei importieren nach Vorschau übernommen werden. Ein fremdes Webseitenformat benötigt einen passenden Adapter.

Online-Refresh entdeckt Archivlinks der aktivierten Quellen, lädt alle verfügbaren Jahrgänge schonend erneut und importiert mit Dublettenschutz. HTTP 403 wird als Zugriffsfehler gemeldet; keine Umgehung. Lokale Archive sind offline importierbar. Keine frei erfundenen Download-URLs. Unveränderte Archive werden nicht doppelt abgelegt; geänderte Originalstände bleiben als getrennte Prüfsummenbelege erhalten. Auch CLI --update berücksichtigt die gespeicherte Quellenwahl.

## Status

Umgesetzt und technisch getestet – Benutzerkontrolle ausstehend. Acht zusätzliche Sprach-/Hilfepakete und Veröffentlichungs-ZIP werden nach der Kontrolle des endgültigen DE/EN-Programms bereitgestellt. Kein GitHub-Repository oder Updatepfad ist bisher nachgewiesen; Quellen für Updates/Sprachen bleiben leer und sind nicht vom Benutzer editierbar. Kein DEB beauftragt. Prüfungen und Einschränkungen stehen in `PRUEFBERICHT.md`.

## Private Quellenarchive

Josefs Quellenordner `sources/` bleibt ausschließlich im privaten Arbeitsordner. Die Ausschlüsse sind in `projekt.json` unter `distribution_policy` festgehalten; `.gitignore` verhindert eine gewöhnliche Git-Aufnahme. Bei späterer ZIP-/DEB-/GitHub-Paketierung diese Ausschlüsse verbindlich anwenden und den tatsächlichen Inhalt prüfen. Aktuell wurde kein Auslieferungspaket erzeugt. Die Datenbank mit Ziehungen und Quoten gehört weiterhin zu den Programmfunktionen; persönliche Tippserien und Einstellungen dürfen nicht als öffentliche Standarddaten ausgeliefert werden. Ein bewusster Online-Abruf durch den Benutzer kann die öffentlich erreichbaren Quelldaten erneut herunterladen.
