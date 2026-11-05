"""
Die "Werkzeuge" von Jarvis.

Claude (das Gehirn) kann selbst nichts am PC tun. Stattdessen beschreiben wir ihm
hier Werkzeuge ("Tools"). Wenn Claude eins benutzen will, sagt er uns welches und
mit welchen Angaben – und dieser Code führt es dann wirklich aus.

Sicherheit: Jarvis kann nur das, was hier steht. Er kann keine beliebigen
Befehle ausführen, nichts löschen (außer eigenen Terminen) und nichts herunterfahren.
"""

import ctypes
import json
import os
import platform
import re
import subprocess
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

import einstellungen
import vollzugriff

IST_WINDOWS = platform.system() == "Windows"

# Tasten-Codes von Windows für Lautstärke und Musik
TASTEN = {
    "lauter": 0xAF, "leiser": 0xAE, "stumm": 0xAD,
    "play_pause": 0xB3, "naechster": 0xB0, "vorheriger": 0xB1,
}


# ---------------------------------------------------------------------------
# 1) Beschreibung der Werkzeuge für Claude
# ---------------------------------------------------------------------------

WERKZEUG_BESCHREIBUNGEN = [
    {
        "name": "termin_eintragen",
        "description": "Speichert eine Erinnerung oder einen Termin. Jarvis meldet sich dann "
                       "zur richtigen Zeit per Sprache. Rechne relative Angaben ('in 10 Minuten', "
                       "'morgen um 9') anhand der aktuellen Zeit in ein festes Datum um.",
        "input_schema": {
            "type": "object",
            "properties": {
                "art": {"type": "string", "enum": ["erinnerung", "termin"]},
                "text": {"type": "string", "description": "Worum es geht, z. B. 'Mama anrufen'"},
                "zeitpunkt": {"type": "string", "description": "Format JJJJ-MM-TTTHH:MM, z. B. 2026-11-06T09:00"},
                "minuten_vorher": {"type": "integer", "description": "Bei Terminen: wie viele Minuten vorher erinnern (Standard 0)"},
            },
            "required": ["art", "text", "zeitpunkt"],
        },
    },
    {
        "name": "termine_anzeigen",
        "description": "Zeigt gespeicherte Erinnerungen und Termine, optional in einem Zeitraum.",
        "input_schema": {
            "type": "object",
            "properties": {
                "von": {"type": "string", "description": "Format JJJJ-MM-TTTHH:MM (optional)"},
                "bis": {"type": "string", "description": "Format JJJJ-MM-TTTHH:MM (optional)"},
            },
        },
    },
    {
        "name": "termin_loeschen",
        "description": "Löscht eine Erinnerung oder einen Termin anhand der ID (vorher mit termine_anzeigen suchen).",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
    {
        "name": "hyperliquid_bericht",
        "description": "Liefert den neuesten Tagesbericht über die Top-Trader auf Hyperliquid: "
                       "was sie in den letzten 24 Stunden gekauft/verkauft haben, wo sie sich einig sind, "
                       "offene Long/Short-Positionen und Statistiken (Gewinnrate, Hebel usw.). "
                       "Benutze das für alle Fragen zu Hyperliquid, Top-Tradern oder was 'die Profis' machen.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "markt_analyse",
        "description": "Technische Analyse eines Marktes aus MetaTrader 5 (FTMO-Konto): Trend auf dem "
                       "Daytrading-Zeitrahmen und auf H1, EMA20/50, RSI, MACD, ATR, Unterstützungen, "
                       "Widerstände und Tages-Pivots. Märkte z. B. EURUSD, Gold, US30, US100, DAX, BTCUSD.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "z. B. 'EURUSD', 'Gold', 'US30'"},
                "zeitrahmen": {"type": "string", "enum": ["M1", "M5", "M15", "M30", "H1", "H4", "D1"],
                               "description": "Standard: Daytrading-Zeitrahmen aus den Einstellungen"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "maerkte_ueberblick",
        "description": "Kurzer Überblick über alle beobachteten Trading-Märkte: Preis, Trend, RSI. "
                       "Für Fragen wie 'Wie sehen die Märkte aus?' oder 'Wo gibt es gerade ein Setup?'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "konto_status",
        "description": "Stand des MetaTrader-5/FTMO-Kontos: Balance, Equity, offene Positionen, Gewinn heute "
                       "und wie viel Luft bis zu den FTMO-Verlustgrenzen und bis zum Gewinnziel bleibt.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tradingview_analyse",
        "description": "Holt die TradingView-'Technical Ratings' (Zusammenfassung aus 26 Indikatoren: "
                       "Kaufen/Verkaufen/Neutral) für M15, H1, H4 und D1 plus RSI, MACD, ADX, ATR, EMAs und "
                       "Monats-Pivots. Für Fragen wie 'Was sagt TradingView zu Gold?'. Geht für Forex, Gold, "
                       "Indizes, Krypto und auch Aktien (z. B. 'NASDAQ:AAPL').",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "z. B. 'XAUUSD', 'DAX', 'EURUSD' oder 'BÖRSE:SYMBOL'"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "setup_scanner",
        "description": "Durchsucht die Trading-Märkte (oder einen bestimmten) nach Daytrading-Setups nach festen "
                       "Regeln (Pullback im H1-Trend, RSI/MACD drehen) und liefert Einstieg, Stop-Loss, Ziel und "
                       "CRV – oder den Grund, warum es gerade kein Setup gibt. Für 'Wo gibt es ein Setup?'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "optional: nur diesen Markt prüfen"},
                "zeitrahmen": {"type": "string", "enum": ["M5", "M15", "M30"], "description": "Standard M15"},
            },
        },
    },
    {
        "name": "positionsgroesse_berechnen",
        "description": "Berechnet die Lotgröße, damit beim Stop-Loss nur ein bestimmter Prozentsatz des Kontos "
                       "verloren geht (Standard 0,5 %). Nutzt die genauen Kontraktdaten aus MT5, wenn verfügbar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"}, "einstieg": {"type": "number"}, "stop": {"type": "number"},
                "risiko_prozent": {"type": "number", "description": "Standard 0.5"},
            },
            "required": ["symbol", "einstieg", "stop"],
        },
    },
    {
        "name": "alarm_setzen",
        "description": "Setzt einen Trading-Alarm. Jarvis beobachtet im Hintergrund und meldet sich per Stimme. "
                       "Arten: preis_ueber, preis_unter, rsi_ueber, rsi_unter (Wert nötig) und setup "
                       "(meldet, sobald der Setup-Scanner ein Setup findet).",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "art": {"type": "string", "enum": ["preis_ueber", "preis_unter", "rsi_ueber", "rsi_unter", "setup"]},
                "wert": {"type": "number"},
                "zeitrahmen": {"type": "string", "enum": ["M1", "M5", "M15", "M30", "H1", "H4"]},
            },
            "required": ["symbol", "art"],
        },
    },
    {
        "name": "alarme_verwalten",
        "description": "Zeigt alle aktiven Trading-Alarme oder löscht einen (mit loeschen_id).",
        "input_schema": {
            "type": "object",
            "properties": {"loeschen_id": {"type": "integer", "description": "optional: diesen Alarm löschen"}},
        },
    },
    {
        "name": "wirtschaftskalender",
        "description": "Wichtige Wirtschafts-News für heute und morgen (Zinsentscheide, NFP, CPI …) mit Uhrzeit. "
                       "Vor jedem Trade sinnvoll: rund um starke News schwanken die Kurse heftig.",
        "input_schema": {
            "type": "object",
            "properties": {
                "alle": {"type": "boolean", "description": "true = auch mittlere Wichtigkeit"},
                "waehrungen": {"type": "array", "items": {"type": "string"}, "description": "z. B. ['USD','EUR']"},
            },
        },
    },
    {
        "name": "chart_zeigen",
        "description": "Zeigt einen Markt im Live-Chart der Jarvis-Zentrale an (TradingView-Chart in der Mitte). "
                       "Benutze das IMMER, wenn der Nutzer einen Chart sehen will ('zeig mir Gold', 'DAX auf H1') – "
                       "nicht den Browser. Geht für alle Märkte, auch Aktien im Format 'BÖRSE:SYMBOL'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "z. B. 'XAUUSD', 'DAX', 'NASDAQ:AAPL'"},
                "zeitrahmen": {"type": "string", "enum": ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "bildschirm_ansehen",
        "description": "Macht einen Screenshot des Bildschirms und zeigt ihn dir, damit du sehen kannst, was der "
                       "Nutzer sieht – z. B. seinen TradingView-Chart mit eingezeichneten Linien, Mustern und "
                       "Indikatoren. Nur benutzen, wenn der Nutzer dich bittet, etwas anzusehen "
                       "('schau dir meinen Chart an', 'was siehst du').",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tagebuch_eintragen",
        "description": "Trägt einen Trade ins Trading-Tagebuch ein. Mit Einstieg, Stop und Ausstieg wird das "
                       "Ergebnis in R (Vielfache des Risikos) automatisch berechnet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"}, "richtung": {"type": "string", "enum": ["LONG", "SHORT"]},
                "einstieg": {"type": "number"}, "stop": {"type": "number"}, "ausstieg": {"type": "number"},
                "gewinn": {"type": "number", "description": "Gewinn/Verlust in Kontowährung (negativ = Verlust)"},
                "setup": {"type": "string", "description": "z. B. 'Pullback EMA20'"},
                "notiz": {"type": "string", "description": "Gedanken, Fehler, Gefühl"},
            },
            "required": ["symbol", "richtung"],
        },
    },
    {
        "name": "tagebuch_auswertung",
        "description": "Wertet das Trading-Tagebuch aus: Trefferquote, Ergebnis in R, Gewinn, pro Markt; "
                       "und listet die letzten Trades. Für 'Wie lief meine Woche?' oder 'Was mache ich falsch?'.",
        "input_schema": {
            "type": "object",
            "properties": {"tage": {"type": "integer", "description": "Zeitraum in Tagen, Standard 30"}},
        },
    },
    {
        "name": "trader_status",
        "description": "Stand des Trading-Roboters (Paper-Trading): Status, Stufe, Konto, heutiges Ergebnis, "
                       "offene Positionen, Statistik und die letzten Entscheidungen MIT Begründung. Für 'Wie läuft "
                       "der Roboter?', 'Warum hast du Gold gekauft?' oder 'Warum handelst du nicht?'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "trader_steuern",
        "description": "Steuert den Trading-Roboter: 'pause' (keine neuen Trades), 'fortsetzen', 'notaus' "
                       "(alle Paper-Positionen schließen und stoppen) oder 'zuruecksetzen' (Paper-Konto neu "
                       "starten). Fortsetzen und Zurücksetzen nur nach Freigabe des Nutzers.",
        "input_schema": {
            "type": "object",
            "properties": {"aktion": {"type": "string", "enum": ["pause", "fortsetzen", "notaus", "zuruecksetzen"]}},
            "required": ["aktion"],
        },
    },
    {
        "name": "backtest_starten",
        "description": "Testet die Trading-Strategie des Roboters auf historischen Kursen (M15, so weit die Daten "
                       "reichen) mit Kosten, Risiko-Engine, Kalibrierung des Confidence-Scores, Stabilitäts- und "
                       "Monte-Carlo-Prüfung. Liefert ein Urteil (bestanden / nicht bestanden / zu wenig Daten).",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "z. B. 'XAUUSD'; leer = alle Roboter-Märkte"}},
        },
    },
    {
        "name": "trading_tagesbericht",
        "description": "Der tägliche Trading-Bericht des Roboters (Marktübersicht, Trades, Performance, "
                       "Strategieanalyse) für heute oder ein Datum (JJJJ-MM-TT).",
        "input_schema": {"type": "object", "properties": {"datum": {"type": "string"}}},
    },
    {
        "name": "an_claude_melden",
        "description": "Meldet Claude (deinem Entwickler in Claude Code) deine EIGENEN Änderungen: selbst "
                       "geänderte Programmdateien, selbstgebaute Werkzeuge und Einstellungen werden mit deiner "
                       "Nachricht in den GitHub-Zweig 'jarvis-pc' hochgeladen. Benutze das, nachdem du dich "
                       "selbst verändert hast, oder wenn der Nutzer sagt 'sag Claude Bescheid'. Der Nutzer "
                       "bestätigt das Hochladen.",
        "input_schema": {
            "type": "object",
            "properties": {"nachricht": {"type": "string",
                                         "description": "Was du geändert hast und warum – für Claude"}},
            "required": ["nachricht"],
        },
    },
    {
        "name": "neuigkeiten",
        "description": "Zeigt, was Claude zuletzt an dir verbessert hat (NEUIGKEITEN.md) und prüft, ob auf "
                       "GitHub ein neues Update wartet. Für 'Was ist neu?' oder 'Gibt es ein Update?'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "mt5_zugang_speichern",
        "description": "Speichert die MetaTrader-5-Zugangsdaten (z. B. FTMO) dauerhaft in Jarvis' .env-Datei "
                       "und testet sofort die Verbindung. Benutze das, wenn der Nutzer dir Login, Passwort und "
                       "Server gibt. Wiederhole das Passwort niemals in deiner Antwort.",
        "input_schema": {
            "type": "object",
            "properties": {
                "login": {"type": "string", "description": "Kontonummer, nur Ziffern"},
                "passwort": {"type": "string"},
                "server": {"type": "string", "description": "z. B. 'FTMO-Demo'"},
            },
            "required": ["login", "passwort", "server"],
        },
    },
    {
        "name": "programm_oeffnen",
        "description": "Öffnet ein Programm oder eine App, die auf dem PC installiert ist "
                       "(alles aus dem Startmenü, z. B. Discord, Steam, WhatsApp, Spotify, Word, "
                       "Rechner, Editor). Kurznamen: " + ", ".join(einstellungen.PROGRAMME),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Name des Programms, z. B. 'Discord'"}},
            "required": ["name"],
        },
    },
    {
        "name": "programm_schliessen",
        "description": "Schließt ein geöffnetes Programm-Fenster (wie auf das X klicken – ungespeicherte "
                       "Arbeit wird vorher abgefragt).",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "z. B. 'Chrome', 'Spotify', 'Rechner'"}},
            "required": ["name"],
        },
    },
    {
        "name": "youtube_abspielen",
        "description": "Sucht auf YouTube und spielt das erste passende Video sofort ab. "
                       "Benutze das für alles wie 'spiel/öffne ein Video von ...', 'zeig mir ... auf YouTube'.",
        "input_schema": {
            "type": "object",
            "properties": {"suche": {"type": "string", "description": "Suchbegriff, z. B. 'Haftbefehl Chabos wissen wer der Babo ist'"}},
            "required": ["suche"],
        },
    },
    {
        "name": "spotify_suchen",
        "description": "Öffnet Spotify mit einer Suche nach Künstler, Song oder Playlist.",
        "input_schema": {
            "type": "object",
            "properties": {"suche": {"type": "string"}},
            "required": ["suche"],
        },
    },
    {
        "name": "webseite_oeffnen",
        "description": "Öffnet eine Webseite im Standard-Browser (z. B. für 'öffne YouTube' oder eine Google-Suche).",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Vollständige Adresse mit https://"}},
            "required": ["url"],
        },
    },
    {
        "name": "medien_steuern",
        "description": "Steuert Lautstärke und Musik am PC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aktion": {"type": "string", "enum": list(TASTEN)},
                "stufen": {"type": "integer", "description": "Bei lauter/leiser: wie viele Stufen (1 Stufe = 2 %). Standard 5."},
            },
            "required": ["aktion"],
        },
    },
    {
        "name": "datei_suchen",
        "description": "Sucht Dateien nach Namen in Desktop, Dokumente, Downloads, Bilder und Musik.",
        "input_schema": {
            "type": "object",
            "properties": {"suchbegriff": {"type": "string"}},
            "required": ["suchbegriff"],
        },
    },
    {
        "name": "datei_oeffnen",
        "description": "Öffnet eine Datei, die vorher mit datei_suchen gefunden wurde.",
        "input_schema": {
            "type": "object",
            "properties": {"pfad": {"type": "string"}},
            "required": ["pfad"],
        },
    },
    {
        "name": "pc_sperren",
        "description": "Sperrt den Bildschirm (wie Windows-Taste + L).",
        "input_schema": {"type": "object", "properties": {}},
    },
]

# Websuche läuft direkt bei Anthropic (kein eigener Code nötig)
WEBSUCHE = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3,
            "user_location": {"type": "approximate", "country": "DE", "timezone": "Europe/Berlin"}}


def alle_werkzeuge(plugins=None):
    werkzeuge = list(WERKZEUG_BESCHREIBUNGEN)
    if einstellungen.VOLLZUGRIFF:
        werkzeuge += vollzugriff.BESCHREIBUNGEN
        werkzeuge += [m.WERKZEUG for m in (plugins or {}).values()]
    if einstellungen.WEBSUCHE_ERLAUBT:
        werkzeuge.append(WEBSUCHE)
    return werkzeuge


# ---------------------------------------------------------------------------
# 2) Die echte Ausführung
# ---------------------------------------------------------------------------

class Werkzeugkasten:
    def __init__(self, kalender, bestaetigen=None):
        self.kalender = kalender
        # Fragt den Nutzer, ob eine riskante Aktion ausgeführt werden darf -> True/False
        self.bestaetigen = bestaetigen or (lambda art, beschreibung, details: False)
        self.plugins = vollzugriff.plugins_laden() if einstellungen.VOLLZUGRIFF else {}
        self.werkzeuge_geaendert = False  # wird True, wenn ein neues Plugin dazukam
        self._alarm_system = None

    def alarme_starten(self):
        """Startet die Alarm-Beobachtung, falls gespeicherte Alarme existieren (beim Programmstart)."""
        if (einstellungen.DATEN_ORDNER / "alarme.json").exists():
            self._alarme()

    def werkzeug_liste(self):
        return alle_werkzeuge(self.plugins)

    def ausfuehren(self, name, eingaben):
        """Führt ein Werkzeug aus und gibt einen Text als Ergebnis für Claude zurück."""
        if name in self.plugins:
            return str(self.plugins[name].ausfuehren(**eingaben))
        funktion = getattr(self, f"_{name}", None)
        if funktion is None:
            raise ValueError(f"Unbekanntes Werkzeug: {name}")
        return funktion(**eingaben)

    # ---------- Vollzugriff ----------

    def _befehl_ausfuehren(self, befehl, zweck=""):
        if not einstellungen.VOLLZUGRIFF:
            return "Vollzugriff ist in den Einstellungen ausgeschaltet."
        return vollzugriff.befehl_ausfuehren(befehl, zweck, self.bestaetigen)

    def _jarvis_aktualisieren(self):
        return vollzugriff.jarvis_aktualisieren(self.bestaetigen)

    def _werkzeug_erstellen(self, name, zweck, python_code):
        if not einstellungen.VOLLZUGRIFF:
            return "Vollzugriff ist in den Einstellungen ausgeschaltet."
        eingebaut = {w["name"] for w in WERKZEUG_BESCHREIBUNGEN + vollzugriff.BESCHREIBUNGEN} | {"web_search"}
        ergebnis = vollzugriff.werkzeug_erstellen(name, zweck, python_code, self.bestaetigen, eingebaut)
        if ergebnis.startswith("Werkzeug „"):
            self.plugins = vollzugriff.plugins_laden()
            self.werkzeuge_geaendert = True
        return ergebnis

    # ---------- Termine ----------

    def _termin_eintragen(self, art, text, zeitpunkt, minuten_vorher=0):
        e = self.kalender.hinzufuegen(art, text, zeitpunkt, minuten_vorher)
        return f"Gespeichert (ID {e['id']}): {e['art']} '{e['text']}' am {e['zeit']}, Meldung um {e['melden_um']}."

    def _termine_anzeigen(self, von=None, bis=None):
        eintraege = self.kalender.auflisten(von=von, bis=bis)
        if not eintraege:
            return "Keine Einträge gefunden."
        return "\n".join(f"ID {e['id']}: {e['art']} '{e['text']}' am {e['zeit']}"
                         + (" (schon gemeldet)" if e["gemeldet"] else "") for e in eintraege)

    def _termin_loeschen(self, id):
        return "Gelöscht." if self.kalender.loeschen(id) else f"Kein Eintrag mit ID {id} gefunden."

    # ---------- Hyperliquid ----------

    def _hyperliquid_bericht(self):
        lokal = Path(einstellungen.HYPERLIQUID_BERICHT_LOKAL)
        # Ein lokaler Bericht, der jünger als 26 Stunden ist, wird bevorzugt
        if lokal.exists() and time.time() - lokal.stat().st_mtime < 26 * 3600:
            text, quelle = lokal.read_text(encoding="utf-8"), "lokaler Bericht"
        else:
            url, kopf = einstellungen.HYPERLIQUID_BERICHT_URL, {"User-Agent": "jarvis"}
            if os.environ.get("GITHUB_TOKEN"):  # privates Repository
                url = "https://api.github.com/repos/YusufAydar/Jarvzz/contents/berichte/aktuell.md?ref=main"
                kopf.update({"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                             "Accept": "application/vnd.github.raw"})
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=kopf), timeout=20) as antwort:
                    text, quelle = antwort.read().decode("utf-8"), "Bericht von GitHub"
            except Exception as fehler:
                if lokal.exists():
                    text, quelle = lokal.read_text(encoding="utf-8"), "älterer lokaler Bericht"
                else:
                    return (f"Kein Hyperliquid-Bericht verfügbar ({fehler}). Der Bericht entsteht, "
                            "sobald die GitHub Action gelaufen ist oder 'python main.py' gestartet wurde.")
        return f"[Quelle: {quelle}]\n\n{text[:20000]}"

    # ---------- Trading (nur lesen) ----------

    def _markt_analyse(self, symbol, zeitrahmen=None):
        from trading import indikatoren, marktdaten
        zeitrahmen = (zeitrahmen or einstellungen.TRADING_ZEITRAHMEN).upper()
        try:
            sym, stellen, quelle, kerzen = marktdaten.kerzen_holen(symbol, zeitrahmen, 300)
        except Exception as fehler:
            return f"Keine Kursdaten für {symbol}: {fehler}"
        kerzen_h1 = tage = None
        try:
            kerzen_h1 = marktdaten.kerzen_holen(symbol, "H1", 200)[3] if zeitrahmen != "H1" else None
            tage = marktdaten.kerzen_holen(symbol, "D1", 3)[3]
        except Exception:
            pass
        a = indikatoren.analysiere(kerzen, kerzen_h1, vortag=tage[-2] if tage and len(tage) >= 2 else None)
        return f"[Quelle: {quelle}]\n" + indikatoren.zusammenfassung(sym, zeitrahmen, a, stellen)

    def _maerkte_ueberblick(self):
        from trading import indikatoren, marktdaten
        zeilen = []
        for name in einstellungen.TRADING_MAERKTE:
            try:
                sym, stellen, quelle, kerzen = marktdaten.kerzen_holen(name, einstellungen.TRADING_ZEITRAHMEN, 200)
                h1 = marktdaten.kerzen_holen(name, "H1", 200)[3]
            except Exception as fehler:
                zeilen.append(f"{name}: {fehler}")
                continue
            schluss = [k["close"] for k in kerzen]
            r = indikatoren.rsi(schluss)[-1]
            zeilen.append(f"{sym}: {schluss[-1]:.{stellen}f} | {einstellungen.TRADING_ZEITRAHMEN} "
                          f"{indikatoren.trend(kerzen)} | H1 {indikatoren.trend(h1)} | RSI {r:.0f} [{quelle}]")
        return "\n".join(zeilen)

    def _tradingview_analyse(self, symbol):
        from trading import kursquellen, tradingview
        ticker = kursquellen.tradingview_kuerzel(symbol)
        if not ticker:
            return (f"Ich kenne das TradingView-Kürzel für '{symbol}' nicht. Bitte im Format BÖRSE:SYMBOL "
                    "angeben, z. B. 'OANDA:XAUUSD' oder 'NASDAQ:AAPL'.")
        try:
            return tradingview.zusammenfassung(symbol, tradingview.analyse(ticker))
        except Exception as fehler:
            return f"TradingView gerade nicht erreichbar ({type(fehler).__name__}: {fehler})."

    def _setup_scanner(self, symbol=None, zeitrahmen="M15"):
        from trading import marktdaten, setups
        zeilen = []
        for name in ([symbol] if symbol else einstellungen.TRADING_MAERKTE):
            try:
                _, stellen, quelle, kerzen = marktdaten.kerzen_holen(name, zeitrahmen, 300)
                h1 = marktdaten.kerzen_holen(name, "H1", 200)[3]
            except Exception as fehler:
                zeilen.append(f"{name}: keine Daten ({fehler})")
                continue
            zeilen.append(setups.setup_text(setups.finde_setup(kerzen, h1, name, stellen), stellen)
                          + f" [{zeitrahmen}, {quelle}]")
        return "\n".join(zeilen) + "\n(Regel-basierte Kandidaten, keine Garantie. Vor dem Einstieg News prüfen.)"

    def _positionsgroesse_berechnen(self, symbol, einstieg, stop, risiko_prozent=0.5):
        from trading import mt5_verbindung as mt
        from trading import setups
        wert = schritt = None
        konto = einstellungen.FTMO_KONTOGROESSE
        try:
            wert, schritt = mt.kontrakt_info(symbol)
            konto = mt.kontostand()["equity"]
        except Exception:
            pass
        r = setups.positionsgroesse(konto, risiko_prozent, einstieg, stop, wert, schritt or 0.01, symbol)
        text = (f"Risiko {risiko_prozent} % von {konto:.0f} = {r['risiko_betrag']:.2f}. "
                f"Abstand Einstieg–Stop: {r['abstand']}.")
        if r["lots"] is None:
            return text + (" Für die Lotgröße brauche ich die Kontraktdaten aus MT5 (für dieses Symbol gibt es "
                           "keinen sicheren Standardwert). MT5 öffnen und erneut fragen.")
        return text + (f" Lotgröße: {r['lots']} Lot (tatsächliches Risiko {r['tatsaechliches_risiko']:.2f}, "
                       f"Quelle: {r['quelle']}).")

    def _alarme(self):
        if getattr(self, "_alarm_system", None) is None:
            from trading import alarme, marktdaten
            self._alarm_system = alarme.Alarme(einstellungen.DATEN_ORDNER / "alarme.json", marktdaten.kerzen_holen)
            alarme.waechter_starten(self._alarm_system, lambda text: self.melden(text))
        return self._alarm_system

    def melden(self, text):
        """Meldet etwas von selbst (Alarme). Die Oberfläche ersetzt das durch ihre eigene Funktion."""
        from stimme import sprechen
        sprechen(text)

    def _alarm_setzen(self, symbol, art, wert=None, zeitrahmen="M15"):
        a = self._alarme().hinzufuegen(symbol, art, wert, zeitrahmen)
        return "Alarm gesetzt: " + self._alarme().beschreibung(a)

    def _alarme_verwalten(self, loeschen_id=None):
        if loeschen_id is not None:
            return "Gelöscht." if self._alarme().loeschen(loeschen_id) else f"Keinen Alarm mit ID {loeschen_id}."
        aktiv = self._alarme().aktive()
        return "\n".join(self._alarme().beschreibung(a) for a in aktiv) if aktiv else "Keine aktiven Alarme."

    # ---------- Trading-Roboter ----------
    trader = None  # die Zentrale setzt hier die laufende TradingEngine ein

    def _trader_status(self):
        if self.trader is None:
            return "Der Trading-Roboter läuft nur in der Trading-Zentrale (jarvis_zentrale)."
        d = self.trader.status_daten()
        s = d["statistik"]
        f = lambda x, n=2: "–" if x is None else ("∞" if x == float("inf") else f"{x:.{n}f}")
        zeilen = [f"Roboter: {d['status'].upper()}" + (f" ({d['grund']})" if d["grund"] else "")
                  + f", Stufe {d['stufe']} (PAPER – keine echten Orders), Handelszeit "
                  + ("aktiv" if d["in_handelszeit"] else "vorbei/noch nicht"),
                  f"Paper-Konto: {d['equity']:.2f} $ (Start {d['start']} $), heute {d['heute']:+.2f} $",
                  f"Gesamt: {s['trades']} Trades, Win-Rate {f((s['win_rate'] or 0) * 100, 0)} %, "
                  f"Profit-Faktor {f(s['profit_faktor'])}, max. Drawdown {s['max_drawdown_prozent']:.1f} %"]
        for p in d["offene"]:
            zeilen.append(f"Offen: {p['symbol']} {p['richtung']} ab {p['einstieg']}, Stop {p['stop']}, Ziel {p['ziel']}, "
                          f"aktuell {p['stand']:+.2f} $, Confidence {p['confidence']}")
        for symbol, info in d["markt_info"].items():
            if info.get("fehler") or info.get("veraltet"):
                zeilen.append(f"{symbol}: {info.get('fehler') or 'Daten veraltet'}")
        zeilen.append("Letzte Entscheidungen:")
        for e in d["entscheidungen"][:8]:
            zeilen.append(f"- {datetime.fromtimestamp(e['zeit']):%H:%M} {e['symbol']} {e['aktion']}"
                          + (f" (Confidence {e['confidence']})" if e.get("confidence") else "")
                          + ": " + " | ".join(e["gruende"][:3]))
        return "\n".join(zeilen)

    def _trader_steuern(self, aktion):
        if self.trader is None:
            return "Der Trading-Roboter läuft nur in der Trading-Zentrale."
        if aktion in ("fortsetzen", "zuruecksetzen") and not self.bestaetigen(
                "trader", f"Trading-Roboter: {aktion}",
                "Fortsetzen: der Roboter darf wieder Paper-Trades eröffnen.\n"
                "Zurücksetzen: das Paper-Konto startet neu (alle Paper-Ergebnisse werden gelöscht)."):
            return "Nicht freigegeben."
        return self.trader.steuern(aktion)

    def _backtest_starten(self, symbol=None):
        from trader import backtest, risiko
        from trading import marktdaten
        regeln = risiko.Regeln(einstellungen)
        texte = []
        for markt in ([symbol] if symbol else einstellungen.TRADER_MAERKTE):
            try:
                _, _, quelle, kerzen = marktdaten.kerzen_holen(markt, "M15", 20000)
                try:
                    h1 = marktdaten.kerzen_holen(markt, "H1", 5000)[3]
                except Exception:
                    h1 = None
                ergebnis = backtest.backtest(markt.upper(), kerzen, regeln, einstellungen.TRADER_KONTO_START, h1)
                texte.append(f"[Daten: {quelle}]\n" + backtest.text(ergebnis, regeln))
            except Exception as fehler:
                texte.append(f"{markt}: Backtest nicht möglich ({fehler})")
        return "\n\n".join(texte)

    def _trading_tagesbericht(self, datum=None):
        if self.trader is None:
            return "Der Trading-Roboter läuft nur in der Trading-Zentrale."
        from trader import bericht, risiko
        tag = datum or risiko.tagesbeginn(time.time())
        datei = einstellungen.DATEN_ORDNER / "trading_berichte" / f"{tag}.md"
        if datei.exists():
            return datei.read_text(encoding="utf-8")
        return bericht.tagesbericht(self.trader, tag)

    def _an_claude_melden(self, nachricht):
        import sync
        dateien, uebersprungen = sync.lokale_aenderungen()
        liste = "\n".join(f"{d['status']}: {d['pfad']}" for d in dateien) or "(keine geänderten Dateien – nur die Nachricht)"
        if not self.bestaetigen("sync", "Meine Änderungen an Claude melden (GitHub-Zweig jarvis-pc)",
                                f"Nachricht: {nachricht}\n\nDiese Dateien werden hochgeladen:\n{liste}\n\n"
                                "Nie hochgeladen: .env (Schlüssel), daten/ (Termine, Tagebuch).\n"
                                "Achtung: Ist das Repository öffentlich, kann jeder diese Dateien sehen."):
            return "Der Nutzer hat das Hochladen abgelehnt."
        try:
            r = sync.hochladen(nachricht, dateien=dateien, uebersprungen=uebersprungen)
        except sync.SyncFehler as fehler:
            return f"Hochladen fehlgeschlagen: {fehler}"
        text = f"An Claude gemeldet (Commit {r['commit']}): {len(r['dateien'])} Datei(en)."
        if r["uebersprungen"]:
            text += " Nicht hochgeladen: " + ", ".join(f"{p} ({g})" for p, g in r["uebersprungen"])
        return text

    def _neuigkeiten(self):
        import sync
        lokal = sync.neuigkeiten_lokal()[:5]
        text = "Zuletzt von Claude geändert:\n" + "\n".join(
            f"- {e['kopf']}: {' '.join(e['text'].split())[:300]}" for e in lokal) if lokal else "Keine Neuigkeiten-Datei."
        try:
            neu = sync.update_pruefen()
            text += ("\n\nUPDATE VERFÜGBAR:\n" + "\n".join(f"- {e['kopf']}" for e in neu)
                     + "\n(Mit 'Jarvis, aktualisiere dich' installieren.)") if neu else "\n\nDu bist auf dem neuesten Stand."
        except Exception as fehler:
            text += f"\n\nUpdate-Prüfung nicht möglich: {fehler}"
        return text

    def ui_befehl(self, befehl):
        """Schickt einen Befehl an die Oberfläche. Die Zentrale ersetzt das durch ihre eigene Funktion."""
        return False

    def _chart_zeigen(self, symbol, zeitrahmen=None):
        zeitrahmen = (zeitrahmen or einstellungen.TRADING_ZEITRAHMEN).upper()
        if self.ui_befehl({"aktion": "chart", "symbol": symbol, "zeitrahmen": zeitrahmen}):
            return f"Der Chart zeigt jetzt {symbol} auf {zeitrahmen}."
        return ("Die Jarvis-Zentrale ist gerade nicht geöffnet, deshalb kann ich den Chart nicht anzeigen. "
                "Starte Jarvis mit jarvis_zentrale.")

    def _bildschirm_ansehen(self):
        try:
            from PIL import ImageGrab
        except ImportError:
            return "Für Screenshots fehlt das Paket Pillow (aktualisieren.bat ausführen)."
        if not IST_WINDOWS:
            return "Screenshots gehen nur unter Windows."
        import base64
        import io
        bild = ImageGrab.grab(all_screens=False).convert("RGB")
        bild.thumbnail((1568, 1568))  # größer bringt Claude nichts, kostet nur mehr
        puffer = io.BytesIO()
        bild.save(puffer, format="JPEG", quality=80)
        return {"text": f"Screenshot des Bildschirms ({bild.width}x{bild.height}).",
                "bild": base64.b64encode(puffer.getvalue()).decode(), "media_type": "image/jpeg"}

    def _tagebuch(self):
        if getattr(self, "_tagebuch_objekt", None) is None:
            from trading.tagebuch import Tagebuch
            self._tagebuch_objekt = Tagebuch(einstellungen.DATEN_ORDNER / "tagebuch.json")
        return self._tagebuch_objekt

    def _tagebuch_eintragen(self, symbol, richtung, einstieg=None, stop=None, ausstieg=None, gewinn=None,
                            setup="", notiz=""):
        e = self._tagebuch().eintragen(symbol, richtung, einstieg, stop, ausstieg, gewinn, notiz, setup)
        ergebnis = f", Ergebnis {e['r']:+.2f} R" if e["r"] is not None else ""
        return f"Eingetragen (Nr. {e['id']}): {e['symbol']} {e['richtung']}{ergebnis}."

    def _tagebuch_auswertung(self, tage=30):
        from trading.tagebuch import auswertung_text
        tb = self._tagebuch()
        text = auswertung_text(tb.auswertung(tage))
        letzte = tb.liste(tage)[-8:]
        if letzte:
            text += "\nLetzte Trades:\n" + "\n".join(
                f"{e['zeit'][:10]} {e['symbol']} {e['richtung']} "
                + (f"{e['r']:+.2f} R " if e["r"] is not None else "")
                + (f"{e['gewinn']:+.2f} " if e["gewinn"] is not None else "") + (e["notiz"] or "")
                for e in letzte)
        return text

    def _wirtschaftskalender(self, alle=False, waehrungen=None):
        from trading import kalender
        try:
            liste = kalender.heute_und_morgen(nur_wichtig=not alle, waehrungen=waehrungen)
        except Exception as fehler:
            return f"Wirtschaftskalender gerade nicht erreichbar ({fehler})."
        return kalender.zusammenfassung(liste, "Wichtige News heute und morgen")

    def _mt5_zugang_speichern(self, login, passwort, server):
        login = str(login).strip()
        if not login.isdigit():
            return "Die Login-Nummer darf nur aus Ziffern bestehen."
        if not self.bestaetigen("einstellung", f"MT5-Zugang speichern: Login {login}, Server {server}",
                                "Login, Passwort und Server werden in jarvis/.env gespeichert "
                                "(nur auf diesem PC, das Passwort wird hier nicht angezeigt)."):
            return "Der Nutzer hat das Speichern abgelehnt."
        env_datei_schreiben(einstellungen.JARVIS_ORDNER / ".env",
                            {"MT5_LOGIN": login, "MT5_PASSWORT": passwort, "MT5_SERVER": server.strip()})
        from trading import mt5_verbindung as mt
        mt.neu_verbinden()
        try:
            konto = mt.kontostand()
        except mt.MT5Fehler as fehler:
            return f"Gespeichert, aber die Verbindung klappt noch nicht: {fehler}"
        return (f"Gespeichert und verbunden mit Konto {konto['login']} ({konto['server']}), "
                f"Balance {konto['balance']:.2f} {konto['waehrung']}.")

    def _konto_status(self):
        from trading import mt5_verbindung as mt
        try:
            konto = mt.kontostand()
        except mt.MT5Fehler as fehler:
            return f"MetaTrader 5: {fehler}"
        groesse = einstellungen.FTMO_KONTOGROESSE
        start = mt.tagesstart_balance(konto["balance"])
        p = mt.ftmo_pruefung(konto, start, groesse)
        w = konto["waehrung"]
        zeilen = [
            f"Konto {konto['login']} ({konto['server']}): Balance {konto['balance']:.2f} {w}, "
            f"Equity {konto['equity']:.2f} {w}",
            f"Heute: {p['gewinn_heute']:+.2f} {w} | Ampel: {p['ampel'].upper()}",
            f"Luft bis eigene Tagesgrenze ({einstellungen.SICHERHEIT_TAGESVERLUST} %): "
            f"{p['rest_tagesverlust_sicher']:.2f} {w}; bis FTMO-Tagesgrenze: {p['rest_tagesverlust_ftmo']:.2f} {w}",
            f"Luft bis FTMO-Gesamtgrenze: {p['rest_gesamtverlust']:.2f} {w}",
            f"Bis zum Gewinnziel: {p['bis_ziel']:.2f} {w} ({p['fortschritt_ziel_prozent']:.0f} % geschafft)",
        ]
        if konto["positionen"]:
            zeilen.append("Offene Positionen: " + "; ".join(
                f"{x['symbol']} {x['richtung']} {x['volumen']} Lot ab {x['einstieg']}, "
                f"SL {x['sl'] or 'KEINER'}, Gewinn {x['gewinn']:+.2f}" for x in konto["positionen"]))
        else:
            zeilen.append("Keine offenen Positionen.")
        return "\n".join(zeilen)

    # ---------- PC-Steuerung ----------

    def _programm_oeffnen(self, name):
        if not IST_WINDOWS:
            return "Programme öffnen geht nur unter Windows."
        ziel = einstellungen.PROGRAMME.get(name.lower().strip())
        if ziel is not None:
            # "start" findet Programme wie chrome, winword usw. und auch Links wie spotify:
            subprocess.Popen(["cmd", "/c", "start", "", ziel], shell=False)
            return f"{name} wird geöffnet."
        # Sonst: im Startmenü suchen (findet alle installierten Programme und Store-Apps)
        app = finde_app(name, startmenue_apps())
        if app is None:
            return f"Ich habe kein Programm namens '{name}' im Startmenü gefunden."
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app['AppID']}"])
        return f"{app['Name']} wird geöffnet."

    def _programm_schliessen(self, name):
        if not IST_WINDOWS:
            return "Programme schließen geht nur unter Windows."
        # Fenster finden, deren Programm- oder Fenstername passt, und höflich schließen
        skript = (
            "$n = $env:JARVIS_NAME; "
            "Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and "
            "($_.ProcessName -like \"*$n*\" -or $_.MainWindowTitle -like \"*$n*\") } | "
            "ForEach-Object { [void]$_.CloseMainWindow(); $_.ProcessName }"
        )
        ergebnis = subprocess.run(
            ["powershell", "-NoProfile", "-Command", skript], capture_output=True, text=True,
            env=dict(os.environ, JARVIS_NAME=name.strip()), creationflags=0x08000000, timeout=20)
        geschlossen = sorted(set(ergebnis.stdout.split()))
        if not geschlossen:
            return f"Ich habe kein offenes Fenster für '{name}' gefunden."
        return "Geschlossen: " + ", ".join(geschlossen)

    def _youtube_abspielen(self, suche):
        video_id, titel = youtube_erstes_video(suche)
        if video_id is None:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(suche)
            webbrowser.open(url)
            return "Konnte kein Video direkt finden, habe die YouTube-Suche geöffnet."
        webbrowser.open(f"https://www.youtube.com/watch?v={video_id}")
        return f"Spiele auf YouTube: {titel or suche}"

    def _spotify_suchen(self, suche):
        if not IST_WINDOWS:
            return "Spotify öffnen geht nur unter Windows."
        subprocess.Popen(["cmd", "/c", "start", "", "spotify:search:" + urllib.parse.quote(suche)])
        return f"Spotify-Suche nach '{suche}' geöffnet. Zum Abspielen auf das erste Ergebnis klicken."

    def _webseite_oeffnen(self, url):
        if not url.startswith(("https://", "http://")):
            return "Bitte eine vollständige Adresse mit https:// angeben."
        webbrowser.open(url)
        return f"Geöffnet: {url}"

    def _medien_steuern(self, aktion, stufen=5):
        if not IST_WINDOWS:
            return "Lautstärke und Musik steuern geht nur unter Windows."
        taste = TASTEN[aktion]
        anzahl = max(1, min(int(stufen or 5), 50)) if aktion in ("lauter", "leiser") else 1
        for _ in range(anzahl):
            ctypes.windll.user32.keybd_event(taste, 0, 0, 0)   # Taste drücken
            ctypes.windll.user32.keybd_event(taste, 0, 2, 0)   # Taste loslassen
        return f"Erledigt: {aktion}" + (f" ({anzahl} Stufen)" if anzahl > 1 else "")

    def _datei_suchen(self, suchbegriff):
        begriff = suchbegriff.lower()
        treffer = []
        for ordner in _such_ordner():
            for wurzel, unterordner, dateien in os.walk(ordner):
                # Versteckte Ordner überspringen und nicht zu tief suchen
                unterordner[:] = [u for u in unterordner if not u.startswith(".")]
                if len(Path(wurzel).relative_to(ordner).parts) > 4:
                    unterordner[:] = []
                for datei in dateien:
                    if begriff in datei.lower():
                        treffer.append(str(Path(wurzel) / datei))
                        if len(treffer) >= 10:
                            return "\n".join(treffer)
        return "\n".join(treffer) if treffer else f"Keine Datei mit '{suchbegriff}' gefunden."

    def _datei_oeffnen(self, pfad):
        datei = Path(pfad).expanduser().resolve()
        if not datei.exists():
            return "Diese Datei gibt es nicht."
        if not any(_liegt_in(datei, o) for o in _such_ordner()):
            return "Ich öffne nur Dateien aus Desktop, Dokumente, Downloads, Bilder und Musik."
        if datei.suffix.lower() in (".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".js", ".lnk"):
            return "Programme und Skripte öffne ich aus Sicherheitsgründen nicht."
        if not IST_WINDOWS:
            return "Dateien öffnen geht nur unter Windows."
        os.startfile(str(datei))
        return f"Geöffnet: {datei.name}"

    def _pc_sperren(self):
        if not IST_WINDOWS:
            return "PC sperren geht nur unter Windows."
        ctypes.windll.user32.LockWorkStation()
        return "Bildschirm gesperrt."


def env_datei_schreiben(datei, werte):
    """Setzt Einträge in der .env-Datei (vorhandene werden ersetzt, andere bleiben unverändert)."""
    datei = Path(datei)
    zeilen = datei.read_text(encoding="utf-8").splitlines() if datei.exists() else []
    rest = [z for z in zeilen if z.split("=", 1)[0].strip().lstrip("# ").strip() not in werte]
    rest += [f"{name}={wert}" for name, wert in werte.items()]
    datei.write_text("\n".join(rest) + "\n", encoding="utf-8")
    os.environ.update(werte)


def youtube_erstes_video(suche, html=None):
    """
    Sucht auf YouTube und gibt (video_id, titel) des ersten Videos zurück.
    Funktioniert ohne Anmeldung und ohne API-Schlüssel, indem die Ergebnisseite gelesen wird.
    """
    if html is None:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(suche)
        anfrage = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "de-DE,de;q=0.9",
            "Cookie": "SOCS=CAI; CONSENT=YES+cb",   # überspringt die Cookie-Abfrage
        })
        try:
            with urllib.request.urlopen(anfrage, timeout=15) as antwort:
                html = antwort.read().decode("utf-8", errors="ignore")
        except Exception:
            return None, None
    # Das erste "videoRenderer" ist das erste normale Video (keine Werbung, keine Shorts-Leiste)
    treffer = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}', html)
    if treffer:
        return treffer.group(1), json.loads(f'"{treffer.group(2)}"')
    einfach = re.search(r'"videoId":"([\w-]{11})"', html)
    return (einfach.group(1), None) if einfach else (None, None)


_app_cache = None


def startmenue_apps():
    """Alle Programme und Apps aus dem Startmenü (Name + AppID), einmal geladen."""
    global _app_cache
    if _app_cache is None:
        ergebnis = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", creationflags=0x08000000, timeout=30)
        daten = json.loads(ergebnis.stdout or "[]")
        _app_cache = daten if isinstance(daten, list) else [daten]
    return _app_cache


def finde_app(name, apps):
    """Sucht die passendste App: erst genauer Name, dann Anfang, dann irgendwo enthalten."""
    gesucht = name.lower().strip()
    namen = [(a, a.get("Name", "").lower()) for a in apps]
    for passt in (lambda n: n == gesucht, lambda n: n.startswith(gesucht), lambda n: gesucht in n):
        kandidaten = [a for a, n in namen if passt(n)]
        # Deinstallations- und Hilfe-Einträge überspringen
        kandidaten = [a for a in kandidaten if not re.search(r"uninstall|deinstall|hilfe|help|readme",
                                                              a.get("Name", ""), re.I)]
        if kandidaten:
            return min(kandidaten, key=lambda a: len(a.get("Name", "")))
    return None


def _such_ordner():
    heim = Path.home()
    return [heim / o for o in einstellungen.SUCH_ORDNER if (heim / o).is_dir()]


def _liegt_in(datei, ordner):
    try:
        datei.relative_to(ordner.resolve())
        return True
    except ValueError:
        return False


def aktuelle_zeit_text(jetzt=None):
    jetzt = jetzt or datetime.now()
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    return f"{tage[jetzt.weekday()]}, {jetzt.strftime('%d.%m.%Y %H:%M')} ({jetzt.strftime('%Y-%m-%dT%H:%M')})"
