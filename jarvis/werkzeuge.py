"""
Die "Werkzeuge" von Jarvis.

Claude (das Gehirn) kann selbst nichts am PC tun. Stattdessen beschreiben wir ihm
hier Werkzeuge ("Tools"). Wenn Claude eins benutzen will, sagt er uns welches und
mit welchen Angaben – und dieser Code führt es dann wirklich aus.

Sicherheit: Jarvis kann nur das, was hier steht. Er kann keine beliebigen
Befehle ausführen, nichts löschen (außer eigenen Terminen) und nichts herunterfahren.
"""

import ctypes
import os
import platform
import subprocess
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

import einstellungen

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
        "name": "programm_oeffnen",
        "description": "Öffnet ein Programm auf dem PC. Erlaubte Namen: " + ", ".join(einstellungen.PROGRAMME),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
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


def alle_werkzeuge():
    werkzeuge = list(WERKZEUG_BESCHREIBUNGEN)
    if einstellungen.WEBSUCHE_ERLAUBT:
        werkzeuge.append(WEBSUCHE)
    return werkzeuge


# ---------------------------------------------------------------------------
# 2) Die echte Ausführung
# ---------------------------------------------------------------------------

class Werkzeugkasten:
    def __init__(self, kalender):
        self.kalender = kalender

    def ausfuehren(self, name, eingaben):
        """Führt ein Werkzeug aus und gibt einen Text als Ergebnis für Claude zurück."""
        funktion = getattr(self, f"_{name}", None)
        if funktion is None:
            raise ValueError(f"Unbekanntes Werkzeug: {name}")
        return funktion(**eingaben)

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
            try:
                with urllib.request.urlopen(einstellungen.HYPERLIQUID_BERICHT_URL, timeout=20) as antwort:
                    text, quelle = antwort.read().decode("utf-8"), "Bericht von GitHub"
            except Exception as fehler:
                if lokal.exists():
                    text, quelle = lokal.read_text(encoding="utf-8"), "älterer lokaler Bericht"
                else:
                    return (f"Kein Hyperliquid-Bericht verfügbar ({fehler}). Der Bericht entsteht, "
                            "sobald die GitHub Action gelaufen ist oder 'python main.py' gestartet wurde.")
        return f"[Quelle: {quelle}]\n\n{text[:20000]}"

    # ---------- PC-Steuerung ----------

    def _programm_oeffnen(self, name):
        ziel = einstellungen.PROGRAMME.get(name.lower().strip())
        if ziel is None:
            return f"'{name}' ist nicht freigegeben. Erlaubt: {', '.join(einstellungen.PROGRAMME)}"
        if not IST_WINDOWS:
            return "Programme öffnen geht nur unter Windows."
        # "start" findet Programme wie chrome, winword usw. und auch Links wie spotify:
        subprocess.Popen(["cmd", "/c", "start", "", ziel], shell=False)
        return f"{name} wird geöffnet."

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
