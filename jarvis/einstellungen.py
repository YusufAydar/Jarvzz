"""
Einstellungen für Jarvis. Hier kannst du gefahrlos Dinge ändern.
"""

from pathlib import Path

JARVIS_ORDNER = Path(__file__).resolve().parent
PROJEKT_ORDNER = JARVIS_ORDNER.parent

# ---------- Persönlichkeit ----------
# So spricht Jarvis dich an (z. B. "Boss", "Chef", "Yusuf"). Leer lassen = keine feste Anrede.
ANREDE = "Boss"

# ---------- Vollzugriff ----------
# Darf Jarvis beliebige PowerShell-Befehle ausführen und sich selbst neue Werkzeuge bauen?
VOLLZUGRIFF = True
# Vor jedem Befehl / neuen Werkzeug fragen? (False = ohne Nachfrage. NICHT empfohlen: dann kann
# ein falsch verstandener Satz oder eine manipulierte Webseite Schaden auf deinem PC anrichten.)
BEFEHLE_OHNE_NACHFRAGE = False
# So lange wartet Jarvis auf deine Bestätigung (Sekunden), danach gilt es als "nein"
BESTAETIGUNG_SEKUNDEN = 60

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
WAKE_WORT_VARIANTEN = ["jarvis", "javis", "jarvi", "dschawis", "tschawis", "jervis", "jarwis",
                       "service", "servus", "travis", "charvis", "schavis", "jarviss", "garvis",
                       "harvest", "jarwiss"]
# Nach einer Antwort darfst du so viele Sekunden lang OHNE "Jarvis" nachfragen
NACHFRAGE_SEKUNDEN = 10
# Sprache für die Spracherkennung
SPRACHE = "de-DE"
# Unterbrechen: Sprichst du deutlich lauter als normal, während Jarvis redet, hört er auf (Idee von Jarvis).
# Tipp: mit Kopfhörern klappt das am besten (sonst hört das Mikrofon Jarvis' eigene Stimme).
UNTERBRECHEN = True
UNTERBRECHEN_FAKTOR = 3.0          # wie viel lauter als die Umgebung (kleiner = empfindlicher)
UNTERBRECHEN_MIN_SEKUNDEN = 0.35   # so lange musst du am Stück sprechen
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

# ---------- Trading (MetaTrader 5 / FTMO) ----------
# MetaTrader 5 benutzen? (False = Jarvis fasst MT5 gar nicht an)
MT5_AKTIV = True
# Darf Jarvis MT5 selbst starten, wenn es geschlossen ist? (False = nur verbinden, wenn du es geöffnet hast)
MT5_AUTOMATISCH_STARTEN = False
# Deine Märkte – so wie du sie aussprichst. Jarvis findet den genauen Namen beim Broker selbst
# (bei FTMO z. B. "US30.cash").
TRADING_MAERKTE = ["EURUSD", "XAUUSD", "US30", "US100", "GER40", "BTCUSD"]
# Daytrading: Hauptzeitrahmen für Einstiege (H1 wird immer als Überblick dazugenommen)
TRADING_ZEITRAHMEN = "M15"
# Startgröße deines FTMO-Kontos in Kontowährung, z. B. 10000, 25000, 100000
FTMO_KONTOGROESSE = 10000
# FTMO-Regeln in Prozent der Kontogröße (bitte mit deinen Challenge-Bedingungen abgleichen!)
FTMO_MAX_TAGESVERLUST = 5
FTMO_MAX_GESAMTVERLUST = 10
FTMO_GEWINNZIEL = 10
# Unsere eigene, strengere Grenze: ab diesem Tagesverlust (in %) wird für heute nicht mehr gehandelt
SICHERHEIT_TAGESVERLUST = 3

# ---------- Auto-Trader (Trading-Roboter) ----------
# Stufen: 0 = nur Signale, 1 = Paper-Trading (virtuelles Geld), 2 = halbautomatisch, 3 = vollautomatisch.
# Stufe 2 und 3 (echtes Geld) gibt es erst nach bestandenem Backtest + Paper-Trading und eurer Freigabe.
TRADER_AKTIV = True                 # läuft in der Trading-Zentrale mit
TRADER_STUFE = 1                    # 0 oder 1 – höhere Stufen sind noch gesperrt
# US100 vorerst raus: im 2-Jahres-Test haben dort alle vier Strategien verloren (Stand 07.11.2026)
TRADER_MAERKTE = ["XAUUSD", "EURUSD"]
TRADER_KONTO_START = 10000          # simuliertes Konto in USD (FTMO-Größe)
TRADER_RISIKO_PROZENT = 1.0         # Verlust pro Trade, wenn der Stop-Loss getroffen wird
TRADER_TAGESSTOPP_PROZENT = 2.0     # ab diesem Tagesverlust: heute keine neuen Trades
TRADER_MAX_DRAWDOWN_PROZENT = 6.0   # ab diesem Verlust vom Höchststand: Roboter stoppt, bis ihr ihn freigebt
TRADER_MAX_POSITIONEN = 2
TRADER_VERLUSTSERIE_PAUSE = 3       # nach so vielen Verlusten in Folge: Pause bis morgen
TRADER_MIN_CONFIDENCE = 60          # nur Signale ab diesem Score (0–100)
TRADER_MIN_CRV = 1.5                # Chance/Risiko NACH Kosten
# Welche Strategie je Markt? Möglich: pullback, orb_london, orb_newyork, mean_reversion
# Erst umstellen, wenn der 2-Jahres-Vergleich (Workflow "Roboter-Backtest") eine Strategie als BESTANDEN zeigt.
TRADER_STRATEGIE = {"XAUUSD": "pullback", "US100": "pullback", "EURUSD": "pullback"}
# Variante je Markt (Stop-Management/Uhrzeit), siehe trader/strategien.py VARIANTEN. "basis" = unverändert.
TRADER_VARIANTE = {"XAUUSD": "basis", "EURUSD": "basis"}
TRADER_HANDELSZEIT = ("09:00", "21:00")   # österreichische Zeit, Montag bis Freitag
TRADER_SCHLIESSEN_UM = "20:55"      # Daytrading: offene Positionen vor Handelsschluss schließen
TRADER_NEWS_SPERRE_MINUTEN = 30     # keine neuen Trades so viele Minuten vor/nach wichtigen News
TRADER_PRUEF_SEKUNDEN = 60          # so oft schaut der Roboter auf die Märkte
# Geschätzte Kosten pro Trade (Spread + Kommission) in Preis-Einheiten – bitte mit FTMO abgleichen
TRADER_KOSTEN = {"XAUUSD": 0.35, "US100": 2.0, "EURUSD": 0.00012, "US30": 3.0, "BTCUSD": 30.0}
# Kleinste handelbare Menge in Einheiten (Unzen Gold, Index-Punkte, Euro)
TRADER_EINHEITEN_SCHRITT = {"XAUUSD": 1, "US100": 0.1, "EURUSD": 1000, "US30": 0.1, "BTCUSD": 0.01}

# Standard-Risiko pro Trade in Prozent (für Positionsrechner und Setup-Vorschläge)
RISIKO_STANDARD_PROZENT = 0.5
# News-Wächter: so viele Minuten vor wichtigen News warnt Jarvis (0 = aus) ...
NEWS_WARNUNG_MINUTEN = 15
# Telegram (Schlüssel TELEGRAM_TOKEN und TELEGRAM_CHAT_ID stehen in .env): Meldungen auch aufs Handy schicken?
TELEGRAM_MELDUNGEN = True
# ... aber nur für diese Währungen (die deine Märkte bewegen)
NEWS_WAEHRUNGEN = ["USD", "EUR", "GBP"]
# Daytrading: um diese Uhrzeit erinnert Jarvis dich an offene Positionen ("" = aus)
TAGESENDE_ERINNERUNG = "21:45"

# ---------- Oberfläche (Dashboard) ----------
# Farbe der Trading-Zentrale: "rot" oder "blau"
FARBSCHEMA = "rot"
# Für welchen Ort soll das Wetter angezeigt werden?
WETTER_ORT = "Berlin"
# Welche Kurse sollen im Feld "Märkte" stehen? (Namen wie bei Hyperliquid)
MARKT_COINS = ["BTC", "ETH", "SOL", "HYPE"]
# Ab wie viel Prozent Tagesbewegung meldet der "Wächter" einen Kurs
MARKT_ALARM_PROZENT = 5
# Port der Oberfläche (nur auf deinem PC erreichbar)
OBERFLAECHE_PORT = 8765

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

# ---------- Deine eigenen Einstellungen ----------
# Trag deine Änderungen am besten NICHT hier ein, sondern in die Datei meine_einstellungen.py
# (gleicher Aufbau, z. B. WETTER_ORT = "Köln"). Die wird bei Updates nie überschrieben.
try:
    from meine_einstellungen import *  # noqa: F401,F403
except ImportError:
    pass
