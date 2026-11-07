# 🤖 Jarvis – dein Sprachassistent für Windows

Du sagst **„Jarvis, …“**, und er antwortet mit Stimme. Das „Gehirn“ ist **Claude** von Anthropic.

**Was Jarvis kann:**

| Fähigkeit | Beispiel-Sätze |
|---|---|
| 💬 Fragen beantworten | „Jarvis, erklär mir, was ein Hebel beim Trading ist.“ |
| 🌍 Im Internet nachsehen | „Jarvis, wie wird das Wetter morgen in Köln?“ |
| 📈 Hyperliquid-Top-Trader | „Jarvis, was kaufen die Top-Trader gerade?“ / „Wo sind sich die Profis einig?“ |
| ⏰ Erinnerungen | „Jarvis, erinnere mich in 20 Minuten an die Pizza.“ |
| 📅 Termine | „Jarvis, trag morgen um 10 Uhr Zahnarzt ein und erinnere mich 30 Minuten vorher.“ / „Was steht diese Woche an?“ |
| 🖥️ PC steuern | „Jarvis, öffne Discord.“ (jedes Programm aus dem Startmenü) / „Schließ Chrome.“ / „Mach lauter.“ / „Nächstes Lied.“ / „Sperr den PC.“ |
| 📊 Trading (MT5/FTMO) | „Jarvis, analysier Gold.“ / „Wie sehen die Märkte aus?“ / „Wie steht mein FTMO-Konto?“ (nur lesen, noch keine Orders) |
| ▶️ YouTube & Musik | „Jarvis, spiel ein Video von Haftbefehl.“ (startet das erste Video direkt) / „Such Haftbefehl auf Spotify.“ / „Google mal Rezepte für Lasagne.“ |
| 📁 Dateien finden | „Jarvis, such meine Datei mit Rechnung.“ … „Öffne die erste.“ |

Nach einer Antwort kannst du **10 Sekunden lang ohne „Jarvis“** nachfragen.
Zum Beenden: **„Jarvis, beenden“** oder **Strg + C**.

---

## Einrichtung (einmalig, ca. 10 Minuten)

### Schritt 1: Python installieren
1. Gehe auf https://www.python.org/downloads/ und lade die neueste Version herunter.
2. Starte den Installer. **Ganz wichtig:** Setz unten den Haken bei **„Add python.exe to PATH“**.
3. Klicke auf „Install Now“.

### Schritt 2: Das Projekt herunterladen
1. Öffne https://github.com/YusufAydar/Jarvzz
2. Klicke auf den grünen Knopf **„Code“** und dann auf **„Download ZIP“**.
3. Entpacke die ZIP-Datei, z. B. nach `Dokumente\Jarvzz`.

### Schritt 3: API-Schlüssel holen (das „Gehirn“)
1. Gehe auf https://console.anthropic.com und erstelle ein Konto.
2. Unter **Billing** ein paar Euro Guthaben aufladen. Setz am besten auch ein **Ausgabenlimit**,
   z. B. 10 € im Monat. Dann kann nie mehr abgebucht werden.
3. Unter **API Keys** auf **„Create Key“** klicken und den Schlüssel kopieren. Er beginnt mit `sk-ant-`.

### Schritt 4: Jarvis installieren
1. Öffne im entpackten Projekt den Ordner **`jarvis`**.
2. Doppelklicke auf **`installieren.bat`**. Ein schwarzes Fenster installiert alles automatisch.
3. Am Ende öffnet sich der Editor mit der Datei `.env`. Ersetze `sk-ant-hier-deinen-schluessel-einfuegen`
   durch deinen Schlüssel, **speichere** und schließe den Editor.

> 🔒 Die Datei `.env` ist wie ein Passwort: nie weitergeben, nie hochladen.
> Sie ist so eingestellt, dass Git sie automatisch ignoriert.

### Schritt 5: Starten
- **`jarvis_oberflaeche.bat`** doppelklicken: Dashboard mit Reaktor, Wetter, Märkten, Terminen und Log. Mikrofon und Tippen gehen beide. **Empfohlen.**
- **`jarvis_starten.bat`** doppelklicken: nur Sprache, im schwarzen Fenster.
- **`jarvis_text.bat`** doppelklicken: Textmodus, du tippst statt zu sprechen. Gut für den ersten Test.

### 🚀 Die Trading-Zentrale (Haupt-Oberfläche)

Start: **`jarvis_zentrale.bat`** (auch `jarvis_oberflaeche.bat` und deine Verknüpfung starten jetzt die Zentrale).

| Bereich | Was es kann |
|---|---|
| **Live-Chart (Mitte)** | Echter **TradingView-Chart** mit allen Zeichenwerkzeugen. Umschaltbar auf den **Jarvis-Chart** mit Zonen, Pivots und deinen Positionen. Jarvis schaltet ihn per Sprache um: „Jarvis, zeig mir Gold auf H1“. |
| **👁 Schau dir den Chart an** | Jarvis macht einen Screenshot und analysiert, was du in TradingView eingezeichnet hast. |
| **FTMO-Konto** | Balance, Equity, Gewinn heute, Ampel, Ziel- und Tageslimit-Balken (mit MT5). |
| **Watchlist & Laufleiste** | Kurse, Tagesveränderung, Trend M15/H1, RSI. Klick wählt den Markt. |
| **Setup-Scanner** | Daytrading-Setups mit Einstieg, Stop, Ziel und CRV. Ein Klick füllt den Positionsrechner aus. |
| **Positionsrechner** | Lotgröße für dein Risiko (Standard 0,5 %). |
| **Analyse** | TradingView-Rating für M15, H1, H4 und D1 sowie Trend, RSI, MACD, ATR und Zonen. |
| **News** | Wichtige Wirtschaftstermine mit Countdown. Jarvis **warnt 15 Minuten vorher** mit Stimme. |
| **Alarme** | Preis, RSI oder Setup. Jarvis meldet sich von selbst. |
| **Meldungen & Tagebuch** | Warnungen, Termine und dein Trading-Tagebuch mit Trefferquote und Ergebnis in R. |
| **Wächter** | Warnung bei der FTMO-Ampel Gelb/Rot, Erinnerung an offene Positionen am Abend, Hinweis auf Updates. |

Das alte Design startest du mit **`jarvis_altes_design.bat`**.

### 🤖 Der Trading-Roboter (Auto-Trader)

Er läuft in der Zentrale mit und beobachtet **Gold, US100 und EURUSD**. Bei jeder abgeschlossenen 15-Minuten-Kerze entscheidet er **BUY, SELL, HOLD oder WAIT**, immer mit Begründung und **Confidence-Score**. Im Feld **ROBOTER-ENTSCHEIDUNGEN** klickst du eine Entscheidung an und siehst alle Gründe.

- **Stufe 1 = Paper-Trading:** Er handelt nur mit **virtuellem Geld** (10.000 $). **Echte Orders sind gesperrt.**
- **Feste Grenzen** (in `einstellungen.py`, die der Roboter selbst nicht ändern kann): 1 % Risiko pro Trade, 2 % Tagesstopp, 6 % maximaler Drawdown (dann sperrt er sich), höchstens 2 Positionen, Pause nach 3 Verlusten in Folge, keine Trades 30 Minuten um wichtige News, nur 09–21 Uhr, Positionen werden vor Handelsschluss geschlossen.
- **Knöpfe:** ⏸ Pause, ⛔ Not-Aus (schließt alle Paper-Positionen) und 🧪 Backtest (testet die Strategie auf historischen Kursen).
- **Tagesbericht:** Jeden Abend um 21 Uhr in `daten/trading_berichte/`, und Jarvis sagt dir das Ergebnis.
- **Sprachbefehle:** „Jarvis, wie läuft der Roboter?“, „Warum hast du nicht gekauft?“, „Starte einen Backtest“, „Pausiere den Roboter“.
- **Der Weg zu echtem Geld (Stufe 2/3):** Erst wenn der Backtest **bestanden** ist **und** im Paper-Trading mindestens 100 Trades mit Profit-Faktor ≥ 1,3 vorliegen. Freischalten tut ihr, nicht der Roboter.

### 📱 Jarvis aufs Handy (Telegram)

Jarvis schickt dir Trades, News-Warnungen und den Tagesbericht aufs Handy. Du kannst ihm auch schreiben.
1. In Telegram **@BotFather** öffnen → `/newbot` → Namen vergeben → du bekommst einen Schlüssel.
2. In `jarvis/.env` eintragen: `TELEGRAM_TOKEN=dein-schlüssel` → Jarvis neu starten.
3. Deinem neuen Bot `/start` schreiben → er antwortet mit deiner Chat-ID → in `.env`: `TELEGRAM_CHAT_ID=die-zahl` → Jarvis neu starten.
- Befehle: `/status`, `/bericht`, `/pause`, `/weiter`, `/hilfe` – oder einfach eine Frage schreiben.
- Jarvis antwortet **nur deiner Chat-ID**. Freigaben (riskante Aktionen) gibt es weiterhin **nur am PC**.
- Der PC muss an sein und die Trading-Zentrale laufen.

### 🔗 Verbindung zwischen Jarvis und Claude

- **Jarvis → Claude:** Wenn Jarvis sich selbst verändert (ein Werkzeug baut oder Dateien umbaut), meldet er es mit „an Claude melden“. Seine Änderungen landen mit Bericht im GitHub-Zweig `jarvis-pc`, und Claude liest sie vor jeder Änderung.
- **Claude → Jarvis:** Jede Änderung von Claude steht in **`NEUIGKEITEN.md`**. Jarvis prüft regelmäßig auf Updates, meldet sich („Es gibt ein neues Update …“) und kennt danach seine neuen Fähigkeiten. Frag ihn: „Jarvis, was ist neu?“
- **Einrichten (einmalig):** GitHub → Profilbild → *Settings* → *Developer settings* → *Personal access tokens* → *Fine-grained tokens* → *Generate new token*. Name z. B. „Jarvis“. Bei *Repository access* → *Only select repositories* → **Jarvzz**. Bei *Permissions* → *Contents* → **Read and write**. Den Token in die `.env` als `GITHUB_TOKEN=github_pat_...` eintragen.
- Nie hochgeladen werden `.env` (Schlüssel), `daten/` (Termine, Tagebuch) und alles, was nach Passwort aussieht. Vor jedem Hochladen fragt Jarvis nach deiner Freigabe.

### Die Oberfläche (altes Cockpit)

| Feld | Was es zeigt |
|---|---|
| **Reaktor** | Jarvis' Zustand: blau = bereit, grün = hört zu, orange = denkt nach, hell pulsierend = spricht. Darunter das Gespräch und ein Feld zum Tippen. Mit **🎙 MIKRO** schaltest du das Mikrofon an und aus. |
| **Wetter** | Aktuelles Wetter und die nächsten Tage. Den Ort stellst du in `einstellungen.py` bei `WETTER_ORT` ein. |
| **System / Netz** | Auslastung von CPU, Arbeitsspeicher und Festplatte sowie Up- und Download. |
| **Wächter** | Fällige Erinnerungen, große Kursbewegungen (ab 5 %) und deine anstehenden Termine. |
| **Agent-Aktivität** | Was Jarvis gerade macht, z. B. welche Werkzeuge er benutzt. |
| **Märkte** | Live-Kurse von Hyperliquid. Die Coins stellst du in `einstellungen.py` bei `MARKT_COINS` ein. |
| **Briefing** | Wo sich die Top-Trader laut Tagesbericht einig sind. |

Mit der Leiste unten blendest du Felder ein und aus. Die Oberfläche läuft nur auf deinem PC (`127.0.0.1`) und ist von außen nicht erreichbar.

**Nach einem Update** mit neuen Dateien einmal **`aktualisieren.bat`** doppelklicken. Das installiert neue Pakete, deine `.env` bleibt erhalten.

---

## Was macht jede Datei?

| Datei | Wofür ist sie da? |
|---|---|
| `zentrale.py` / `zentrale/index.html` | **Die Trading-Zentrale:** Server mit allen Daten und die Oberfläche mit Live-Chart. |
| `sync.py` | **Verbindung zu Claude:** eigene Änderungen melden, Updates erkennen. |
| `NEUIGKEITEN.md` | Was Claude zuletzt an Jarvis geändert hat. |
| `jarvis_zentrale.bat` / `jarvis_altes_design.bat` | Doppelklicken: Zentrale starten / altes Design starten. |
| `oberflaeche.py` | **Startpunkt mit Dashboard (alt).** Kleiner Webserver nur auf deinem PC, liefert Wetter, Kurse, Systemwerte und leitet deine Befehle an Jarvis weiter. |
| `oberflaeche/index.html` | **Das Aussehen des Dashboards** (Reaktor-Animation, alle Felder). |
| `jarvis_oberflaeche.bat` / `aktualisieren.bat` | Doppelklicken: Dashboard starten / nach einem Update neue Pakete installieren. |
| `jarvis.py` | **Startpunkt.** Hört zu, erkennt „Jarvis“, gibt die Frage ans Gehirn und spricht die Antwort. |
| `gehirn.py` | **Verbindung zu Claude.** Schickt deine Frage hin, führt gewünschte Werkzeuge aus und holt die Antwort. Enthält auch Jarvis' „Persönlichkeit“ (die Anweisung, wie er sich verhalten soll). |
| `werkzeuge.py` | **Was Jarvis tun kann.** Termine, Hyperliquid-Bericht, Programme öffnen, Lautstärke, Musik, Dateien, PC sperren. Jarvis kann *nur*, was hier steht. |
| `termine.py` | **Kalender.** Speichert Erinnerungen und Termine und merkt, wann sie fällig sind. |
| `stimme.py` | **Ohren und Mund.** Mikrofon → Text (Google-Spracherkennung) und Text → Stimme (Windows-Stimme). |
| `vollzugriff.py` | **Befehle und selbstgebaute Werkzeuge**, immer mit deiner Freigabe. |
| `updater.py` / `aktualisieren.bat` | **Updates** von GitHub holen, ohne deine persönlichen Dateien anzufassen. |
| `plugins/` | Werkzeuge, die Jarvis sich selbst gebaut hat (eine `.py`-Datei pro Werkzeug). |
| `meine_einstellungen.py` | Deine eigenen Einstellungen. Bleibt bei Updates erhalten (Vorlage: `meine_einstellungen.beispiel.py`). |
| `trading/` | MetaTrader-5-Anbindung und Indikatoren (Trend, RSI, MACD, Zonen …). |
| `einstellungen.py` | **Alle Einstellungen.** Erlaubte Programme, Sprechtempo, Wake-Wort usw. Hier darfst du ändern. |
| `requirements.txt` | Liste der Zusatz-Pakete, die `installieren.bat` installiert. |
| `.env.beispiel` | Vorlage für deinen geheimen API-Schlüssel. |
| `installieren.bat` | Einmal doppelklicken: installiert alles. |
| `jarvis_starten.bat` / `jarvis_text.bat` | Doppelklicken zum Starten (Sprache / Text). |
| `tests/test_jarvis.py` | Automatische Tests, laufen ohne Mikrofon und ohne Internet. |
| `daten/termine.json` | Entsteht automatisch: deine gespeicherten Termine. Wird nicht hochgeladen. |

---

## 🔓 Vollzugriff: Jarvis macht, was du sagst

Jarvis kann **jeden PowerShell-Befehl** ausführen und sich **selbst neue Werkzeuge bauen**:
- „Jarvis, räum meinen Download-Ordner auf und sortier die Dateien nach Typ.“
- „Jarvis, installier VLC.“
- „Jarvis, bau dir ein Werkzeug, das mir den Bitcoin-Kurs in Euro sagt.“ Das Werkzeug wird als Datei in `plugins/` gespeichert und ist ab dann dauerhaft dabei.

**Sicherung:** Vor jedem Befehl und jedem neuen Werkzeug zeigt Jarvis dir genau, was er tun will. Der Reaktor wird rot, und du klickst **Erlauben** / **Ablehnen** oder sagst „Ja“ / „Nein“. Nach 60 Sekunden ohne Antwort gilt es als „Nein“.
Abschalten kannst du die Nachfrage mit `BEFEHLE_OHNE_NACHFRAGE = True` in `meine_einstellungen.py`. **Das ist nicht empfohlen:** Dann kann ein falsch verstandener Satz oder eine manipulierte Webseite Schaden anrichten.
Ein selbstgebautes Werkzeug entfernst du, indem du seine Datei in `plugins/` löschst.

## 🔄 Updates

- **Doppelklick auf `aktualisieren.bat`**, oder du sagst **„Jarvis, aktualisiere dich“**. Jarvis holt dann die neueste Version von GitHub und installiert neue Pakete. Danach startest du Jarvis neu.
- **Privates Repository?** Dann braucht Jarvis einen Lese-Schlüssel: Auf GitHub → Profilbild → *Settings* → *Developer settings* → *Personal access tokens* → *Fine-grained tokens* → *Generate new token*. Bei *Repository access* nur **Jarvzz** auswählen, bei *Permissions* → *Contents* **Read-only**. Den Token in die `.env` als `GITHUB_TOKEN=github_pat_...` eintragen.
- Vor jedem Update wird der Jarvis-Ordner in `sicherungen/` gesichert. Dateien, die du oder Jarvis selbst geändert habt, bleiben stehen. Die neue Version liegt dann daneben als `.neu`.
- **Nicht** überschrieben werden: `.env` (Schlüssel), `meine_einstellungen.py`, `daten/` (Termine), `plugins/` (selbstgebaute Werkzeuge).

## Anpassen (in `meine_einstellungen.py`)

Kopiere `meine_einstellungen.beispiel.py` und nenne die Kopie **`meine_einstellungen.py`**. Dort trägst du nur ein, was du anders haben willst, z. B. `WETTER_ORT = "Köln"`. Diese Datei bleibt bei Updates erhalten. In `einstellungen.py` siehst du alle möglichen Einstellungen.

- **Neues Programm erlauben:** In `PROGRAMME` eine Zeile ergänzen, z. B. `"discord": "discord:",`.
- **Schneller oder langsamer sprechen:** `SPRECHTEMPO` ändern (-10 bis 10).
- **Gründlicher nachdenken:** `DENKTIEFE = "medium"`. Das ist langsamer und etwas teurer.
- **Websuche aus:** `WEBSUCHE_ERLAUBT = False`.

---

## Was kostet das?

- Für die Spracherkennung und die Windows-Stimme zahlst du nichts.
- Claude rechnet pro Nutzung ab. Ein normales Gespräch kostet meist **unter 1 Cent bis wenige Cent**.
  Mit dem Ausgabenlimit aus Schritt 3 hast du die volle Kontrolle.
- Eine Websuche kostet extra, etwa 1 Cent pro Suche.

---

## Probleme lösen

| Problem | Lösung |
|---|---|
| „python wird nicht erkannt“ | Python neu installieren und den Haken **„Add to PATH“** setzen. |
| Fehler bei `pyaudio` während der Installation | Im Fenster `pip install pipwin` und danach `pipwin install pyaudio` eingeben, oder Python 3.12 verwenden. |
| Jarvis hört nichts | Windows-Einstellungen → Datenschutz → **Mikrofon** → Zugriff für Apps erlauben. Prüfe auch, welches Mikrofon als Standard eingestellt ist. |
| Jarvis reagiert nicht auf „Jarvis“ | Deutlich sprechen. In der Konsole siehst du unter `(gehört: …)`, was er verstanden hat. Wie er „Jarvis“ falsch schreibt, kannst du bei `WAKE_WORT_VARIANTEN` ergänzen. |
| Stimme klingt englisch | Windows-Einstellungen → Zeit und Sprache → Sprache → **Deutsch** → Sprachausgabe installieren. |
| „API-Schlüssel funktioniert nicht“ | Prüfe die Datei `.env`. Steht dort der Schlüssel ohne Leerzeichen? Hast du Guthaben aufgeladen? |

---

## Gut zu wissen

- Jarvis kann **keine beliebigen Befehle** ausführen, nichts löschen (außer seinen eigenen Terminen)
  und den PC nicht herunterfahren. Er öffnet nur freigegebene Programme und Dateien aus deinen
  normalen Ordnern, aber keine Programme oder Skripte (.exe, .bat …).
- Was du sagst, geht zur Spracherkennung an Google und deine Fragen gehen an Anthropic (Claude).
  Sag Jarvis also keine Passwörter.
- Lehnt Claude eine Frage aus Sicherheitsgründen ab, übernimmt automatisch ein anderes
  Claude-Modell („Fallback“).
