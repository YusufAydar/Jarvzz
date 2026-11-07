# Jarvzz

Yusuf und Markos eigener Jarvzz.

Das Repository enthält zwei Teile:

1. **🤖 Jarvis: Sprachassistent für Windows** → Anleitung in [`jarvis/README.md`](jarvis/README.md)
2. **📈 Analyse der Top-Trader auf Hyperliquid** → wird unten erklärt. Jarvis kann diesen Bericht vorlesen.

---

## Hyperliquid Top-Trader-Analyse
Das Programm schaut sich jeden Tag an, was die erfolgreichsten Trader auf
[Hyperliquid](https://app.hyperliquid.xyz) machen, und schreibt dazu einen Bericht.

> ⚠️ Das ist keine Anlageberatung. Das Programm wertet nur öffentliche Daten aus.

---

## Was macht das Programm? (in 3 Schritten)

1. **Rangliste holen:** Es lädt die öffentliche Rangliste von Hyperliquid und nimmt die
   besten Trader. Standard sind die 10 mit dem höchsten Gewinn im letzten Monat.
2. **Daten speichern:** Für jeden dieser Trader lädt es alle Trades und die gerade
   offenen Positionen und speichert sie in einer Datenbank-Datei (`daten/hyperliquid.db`).
3. **Bericht schreiben:** Es rechnet für jeden Trader die Kennzahlen aus und schreibt
   einen Bericht in den Ordner `berichte/`:
   - Was haben die Top-Trader in den **letzten 24 Stunden** gekauft und verkauft?
   - Bei welchen Coins sind sie sich **einig** (fast alle kaufen oder fast alle verkaufen)?
   - Wer ist gerade **Long** oder **Short**?
   - Pro Trader: **Gewinnrate, Gewinn/Verlust, Haltedauer, Lieblings-Coins, Hebel, größter Verlust**

Eine **GitHub Action** führt das jeden Morgen automatisch aus und speichert den Bericht hier im Repo.
Den neuesten Bericht findest du immer unter **[`berichte/aktuell.md`](berichte/aktuell.md)**.

---

## Was macht jede Datei?

| Datei | Wofür ist sie da? |
|---|---|
| `jarvis/` | **Der Sprachassistent Jarvis.** Alle Dateien darin erklärt [`jarvis/README.md`](jarvis/README.md). |
| `main.py` | **Startpunkt.** Ruft alle anderen Teile in der richtigen Reihenfolge auf. Diese Datei startest du. |
| `config.py` | **Einstellungen.** Wie viele Trader, welcher Zeitraum, ab wann „Einigkeit“ gilt usw. Hier kannst du gefahrlos Zahlen ändern. |
| `hyperliquid_api.py` | **Verbindung zu Hyperliquid.** Lädt die Rangliste, die Trades und die offenen Positionen aus dem Internet. |
| `datenbank.py` | **Speichern.** Legt die SQLite-Datenbank an und schreibt die Daten hinein bzw. liest sie wieder aus. |
| `analyse.py` | **Rechnen.** Baut aus den einzelnen Käufen/Verkäufen echte Trades und berechnet alle Kennzahlen und die Einigkeit. |
| `bericht.py` | **Bericht.** Macht aus den Ergebnissen eine schön lesbare Markdown-Datei mit Tabellen. |
| `muster.py` | **Muster der Top-Trader.** Wertet aus, *wie* die Top-Trader handeln (mit/gegen Trend, Pullback/Ausbruch, Uhrzeit, Haltedauer) und was davon Geld bringt → `berichte/muster.md`. Ideen für eigene Regeln, kein Kopieren. |
| `tests/test_projekt.py` | **Automatische Tests.** Prüfen mit ausgedachten Beispiel-Trades, ob die Rechnungen stimmen (ohne Internet). |
| `.github/workflows/taeglicher-bericht.yml` | **Tägliche Automatik.** Sagt GitHub: „Führe das Programm jeden Tag um 06:17 UTC aus und speichere den Bericht.“ |
| `.github/workflows/tests.yml` | **Prüfung bei Änderungen.** Bei jeder Code-Änderung laufen die Tests und ein Probelauf mit 10 echten Tradern. |
| `.gitignore` | Sagt Git, welche Dateien **nicht** hochgeladen werden (z. B. die große Datenbank). |
| `berichte/` | Hier landen die Berichte: `2026-11-05.md` usw. für jeden Tag, `aktuell.md` ist immer der neueste. |
| `daten/` | Hier liegt die Datenbank. Sie entsteht beim ersten Start von selbst. |

---

## Wie benutze ich es?

### Variante 1: Ganz ohne eigenen Computer (empfohlen)

Alles läuft auf GitHub, du musst nichts installieren.

1. Öffne das Repository auf GitHub und klicke oben auf den Reiter **„Actions“**.
2. Links **„Täglicher Bericht“** auswählen.
3. Rechts auf **„Run workflow“** klicken, die Anzahl der Trader eintragen (z. B. `10`) und starten.
4. Nach ein paar Minuten liegt der neue Bericht im Ordner `berichte/`.

Ab dann läuft das jeden Tag von selbst.

### Variante 2: Auf dem eigenen Computer

Du brauchst nur **Python 3.10 oder neuer** ([python.org](https://www.python.org/downloads/)).
Zusätzliche Pakete braucht es nicht. Dann im Projektordner im Terminal:

```bash
python main.py
```

Das analysiert 10 Trader. Weitere Möglichkeiten:

```bash
python main.py --anzahl 100
```

```bash
python main.py --zeitraum allTime
```

```bash
python main.py --nur-bericht
```

- `--anzahl 100` analysiert 100 Trader.
- `--zeitraum allTime` sortiert nach dem Gesamtgewinn statt nach dem Monatsgewinn.
- `--nur-bericht` lädt nichts herunter und erstellt nur den Bericht neu.

Tests starten:

```bash
python -m unittest discover tests -v
```

---

## Von 10 auf 100 Trader umstellen

Fang mit 10 an. Wenn die Berichte gut aussehen:

1. Öffne die Datei `.github/workflows/taeglicher-bericht.yml`.
2. Ändere in beiden Zeilen mit `'10'` bzw. `"10"` die Zahl auf `100`.
3. Speichern (auf GitHub: „Commit changes“). Fertig.

Mit 100 Tradern dauert ein Lauf länger, beim ersten Mal etwa 10–20 Minuten.

---

## Wichtige Begriffe einfach erklärt

- **Wallet:** Das Konto eines Traders, erkennbar an einer Adresse wie `0x1234…abcd`.
- **Fill:** Ein einzelner Kauf oder Verkauf. Ein Trade besteht oft aus mehreren Fills.
- **Trade:** Eine Position von der Eröffnung bis zur Schließung.
- **Long / Short:** Long = auf steigende Kurse setzen, Short = auf fallende Kurse setzen.
- **Gewinnrate:** Wie viel Prozent der Trades mit Gewinn geendet haben.
- **PnL:** „Profit and Loss“ = Gewinn bzw. Verlust in Dollar.
- **Haltedauer:** Wie lange ein Trade im Schnitt offen war.
- **Hebel:** Wie viel größer die Position ist als das eingesetzte Geld (10x = zehnfach).
- **Einigkeit:** Mindestens 3 Trader handeln einen Coin, und mindestens 70 % davon in dieselbe Richtung.

---

## Grenzen (ehrlich gesagt)

- **Historie:** Hyperliquid gibt pro Wallet nur die **letzten 10.000 Trades** heraus. Bei sehr
  aktiven Tradern reichen die Daten deshalb vielleicht nur ein paar Tage zurück. Ab dem ersten Lauf
  sammelt die Datenbank aber jeden Tag die neuen Trades dazu.
- **Hebel:** Die Trade-Historie enthält keinen Hebel. Der Hebel im Bericht stammt aus den
  **gerade offenen** Positionen.
- **Spot-Käufe** (z. B. `@107` oder `PURR/USDC`) zählen beim Volumen mit, aber nicht als Trades.
- Manche Top-Wallets sind Market-Maker oder Bots mit sehr vielen kleinen Trades. Die Zahlen
  sehen bei ihnen anders aus als bei normalen Tradern.
