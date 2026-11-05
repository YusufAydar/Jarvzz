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

### Die Oberfläche

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
| `oberflaeche.py` | **Startpunkt mit Dashboard.** Kleiner Webserver nur auf deinem PC, liefert Wetter, Kurse, Systemwerte und leitet deine Befehle an Jarvis weiter. |
| `oberflaeche/index.html` | **Das Aussehen des Dashboards** (Reaktor-Animation, alle Felder). |
| `jarvis_oberflaeche.bat` / `aktualisieren.bat` | Doppelklicken: Dashboard starten / nach einem Update neue Pakete installieren. |
| `jarvis.py` | **Startpunkt.** Hört zu, erkennt „Jarvis“, gibt die Frage ans Gehirn und spricht die Antwort. |
| `gehirn.py` | **Verbindung zu Claude.** Schickt deine Frage hin, führt gewünschte Werkzeuge aus und holt die Antwort. Enthält auch Jarvis' „Persönlichkeit“ (die Anweisung, wie er sich verhalten soll). |
| `werkzeuge.py` | **Was Jarvis tun kann.** Termine, Hyperliquid-Bericht, Programme öffnen, Lautstärke, Musik, Dateien, PC sperren. Jarvis kann *nur*, was hier steht. |
| `termine.py` | **Kalender.** Speichert Erinnerungen und Termine und merkt, wann sie fällig sind. |
| `stimme.py` | **Ohren und Mund.** Mikrofon → Text (Google-Spracherkennung) und Text → Stimme (Windows-Stimme). |
| `einstellungen.py` | **Alle Einstellungen.** Erlaubte Programme, Sprechtempo, Wake-Wort usw. Hier darfst du ändern. |
| `requirements.txt` | Liste der Zusatz-Pakete, die `installieren.bat` installiert. |
| `.env.beispiel` | Vorlage für deinen geheimen API-Schlüssel. |
| `installieren.bat` | Einmal doppelklicken: installiert alles. |
| `jarvis_starten.bat` / `jarvis_text.bat` | Doppelklicken zum Starten (Sprache / Text). |
| `tests/test_jarvis.py` | Automatische Tests, laufen ohne Mikrofon und ohne Internet. |
| `daten/termine.json` | Entsteht automatisch: deine gespeicherten Termine. Wird nicht hochgeladen. |

---

## Anpassen (in `einstellungen.py`)

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
