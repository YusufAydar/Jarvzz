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

    # ---------- Trading (nur lesen) ----------

    def _markt_analyse(self, symbol, zeitrahmen=None):
        from trading import indikatoren, mt5_verbindung as mt
        zeitrahmen = (zeitrahmen or einstellungen.TRADING_ZEITRAHMEN).upper()
        try:
            sym, kerzen = mt.kerzen(symbol, zeitrahmen, 300)
            _, kerzen_h1 = mt.kerzen(sym, "H1", 200) if zeitrahmen != "H1" else (sym, None)
            _, tage = mt.kerzen(sym, "D1", 3)
        except mt.MT5Fehler as fehler:
            return f"MetaTrader 5: {fehler}"
        a = indikatoren.analysiere(kerzen, kerzen_h1, vortag=tage[-2] if len(tage) >= 2 else None)
        return indikatoren.zusammenfassung(sym, zeitrahmen, a, mt.nachkommastellen(sym))

    def _maerkte_ueberblick(self):
        from trading import indikatoren, mt5_verbindung as mt
        zeilen = []
        for name in einstellungen.TRADING_MAERKTE:
            try:
                sym, kerzen = mt.kerzen(name, einstellungen.TRADING_ZEITRAHMEN, 200)
                _, h1 = mt.kerzen(sym, "H1", 200)
            except mt.MT5Fehler as fehler:
                zeilen.append(f"{name}: {fehler}")
                continue
            schluss = [k["close"] for k in kerzen]
            r = indikatoren.rsi(schluss)[-1]
            zeilen.append(f"{sym}: {schluss[-1]:.{mt.nachkommastellen(sym)}f} | "
                          f"{einstellungen.TRADING_ZEITRAHMEN} {indikatoren.trend(kerzen)} | "
                          f"H1 {indikatoren.trend(h1)} | RSI {r:.0f}")
        return "\n".join(zeilen)

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
