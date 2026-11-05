"""
Einstellungen für Jarvis. Hier kannst du gefahrlos Dinge ändern.
"""

from pathlib import Path

JARVIS_ORDNER = Path(__file__).resolve().parent
PROJEKT_ORDNER = JARVIS_ORDNER.parent

# ---------- KI-Gehirn (Claude) ----------
# Der API-Schlüssel steht NICHT hier, sondern in der Datei jarvis/.env (siehe README).
MODELL = "claude-opus-5-5"
# Wie gründlich Claude nachdenkt: "low" = schnell (gut für Gespräche),
# "medium" / "high" = gründlicher, aber langsamer und teurer.
DENKTIEFE = "low"
# Nach so vielen Minuten ohne Gespräch fängt Jarvis ein neues Gespräch an
# (er "vergisst" dann den bisherigen Verlauf – das spart Kosten).
GESPRAECH_NEU_NACH_MINUTEN = 15
# Darf Jarvis im Internet suchen (z. B. Wetter, Nachrichten)? Kostet etwas extra.
WEBSUCHE_ERLAUBT = True

# ---------- Stimme ----------
WAKE_WORT = "jarvis"
# So schreibt die Spracherkennung "Jarvis" manchmal falsch – zählt trotzdem:
WAKE_WORT_VARIANTEN = ["jarvis", "javis", "jarvi", "dschawis", "tschawis", "jervis", "jarwis"]
# Nach einer Antwort darfst du so viele Sekunden lang OHNE "Jarvis" nachfragen
NACHFRAGE_SEKUNDEN = 10
# Sprache für die Spracherkennung
SPRACHE = "de-DE"
# Sprechgeschwindigkeit der Windows-Stimme (-10 = langsam, 0 = normal, 10 = schnell)
SPRECHTEMPO = 1

# ---------- Erinnerungen & Termine ----------
DATEN_ORDNER = JARVIS_ORDNER / "daten"
TERMINE_DATEI = DATEN_ORDNER / "termine.json"

# ---------- Hyperliquid ----------
# Lokaler Bericht (entsteht, wenn du "python main.py" im Projektordner startest)
HYPERLIQUID_BERICHT_LOKAL = PROJEKT_ORDNER / "berichte" / "aktuell.md"
# Der tägliche Bericht, den die GitHub Action ins Repository speichert
HYPERLIQUID_BERICHT_URL = "https://raw.githubusercontent.com/YusufAydar/Jarvzz/main/berichte/aktuell.md"

# ---------- PC-Steuerung (nur Windows) ----------
# Programme, die Jarvis öffnen darf: "So sagst du es" -> "So heißt es für Windows"
# Du kannst eigene hinzufügen, z. B. "discord": "discord:".
PROGRAMME = {
    "rechner": "calc",
    "taschenrechner": "calc",
    "editor": "notepad",
    "notepad": "notepad",
    "explorer": "explorer",
    "paint": "mspaint",
    "browser": "https://www.google.de",
    "chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "spotify": "spotify:",
    "einstellungen": "ms-settings:",
    "task-manager": "taskmgr",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "teams": "msteams:",
    "youtube": "https://www.youtube.com",
}

# In diesen Ordnern sucht Jarvis nach Dateien (innerhalb deines Benutzerordners)
SUCH_ORDNER = ["Desktop", "Documents", "Dokumente", "Downloads", "Pictures", "Bilder", "Music", "Musik"]
