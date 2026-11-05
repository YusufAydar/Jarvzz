# Jarvzz – Hinweise für Claude

Dieses Repository gehört Yusuf (und Marko). Yusuf ist **Anfänger ohne Programmierkenntnisse**:
Antworten auf Deutsch, kurz, Schritt für Schritt, ohne Fachjargon. Code-Kommentare und Texte auf Deutsch.

## Teile
- `jarvis/` – Jarvis, Sprach- und Trading-Assistent für Windows (Python, Claude-API über das `anthropic`-SDK).
  - `zentrale.py` + `zentrale/index.html` – die **Trading-Zentrale** (Haupt-Oberfläche, lokaler Webserver auf 127.0.0.1:8765).
  - `gehirn.py` (Claude-Schleife, Grundanweisung), `werkzeuge.py` (alle Werkzeuge), `trading/` (Kurse, Indikatoren,
    Setups, Alarme, TradingView, Kalender, Tagebuch, MT5), `vollzugriff.py`, `updater.py`, `sync.py`.
  - `oberflaeche.py` – älteres Dashboard. Auf Yusufs PC hat Jarvis es **selbst umgebaut** (eigenes Design) – der
    Updater überschreibt es dort nicht.
- Hauptverzeichnis: Hyperliquid-Top-Trader-Analyse (`main.py`, Bericht täglich per GitHub Action).

## Verbindung zu Jarvis (WICHTIG – vor jeder Änderung an `jarvis/`)
Jarvis läuft auf Yusufs PC und kann sich selbst verändern (Plugins, eigene Dateien). Er meldet seine Änderungen
mit dem Werkzeug `an_claude_melden` in den Zweig **`jarvis-pc`** (Ordner `jarvis-pc/`, Bericht `jarvis-pc/BERICHT.md`).

1. **Vorher lesen:** `git fetch origin jarvis-pc` und `git show origin/jarvis-pc:jarvis-pc/BERICHT.md`.
   Geänderte/neue Dateien vergleichen, z. B. `git diff HEAD origin/jarvis-pc -- jarvis-pc/`.
   Gute Ideen von Jarvis sauber in `jarvis/` übernehmen (mit Tests), damit sie beim nächsten Update offiziell sind.
2. **Nachher melden:** Jede Änderung an `jarvis/` bekommt oben in `jarvis/NEUIGKEITEN.md` einen neuen Eintrag
   `## JJJJ-MM-TT · Titel` + kurze Beschreibung der neuen Fähigkeiten. Jarvis erkennt daran das Update und kennt
   danach seine neuen Fähigkeiten.
3. **Vor jedem Commit:** `python werkzeuge_entwicklung/versionen_erzeugen.py` ausführen (Prüfsummen für den Updater –
   sonst hält der Updater unveränderte Dateien für „selbst geändert“) und die Tests laufen lassen:
   `cd jarvis && python -m unittest discover tests` sowie im Hauptordner `python -m unittest discover tests`.

## Regeln
- Nie Geheimnisse ins Repo: `.env`, `daten/`, `meine_einstellungen.py`, `plugins/*.py` sind in `.gitignore`.
- Riskante Aktionen von Jarvis (Befehle, neue Werkzeuge, Hochladen) immer nur nach Freigabe des Nutzers.
- Trading: nur Analyse, keine echten Orders ohne ausdrücklichen Wunsch und feste Verlustgrenzen.
- Externe Datenquellen (Yahoo, TradingView-Screener, ForexFactory-Kalender, Hyperliquid) sind in der Cloud-Umgebung
  oft gesperrt – live geprüft wird über `werkzeuge_entwicklung/live_check.py` in GitHub Actions (`tests.yml`).
