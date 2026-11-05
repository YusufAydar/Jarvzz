"""
JARVIS mit Oberfläche (Dashboard).

Starten:  python oberflaeche.py      (oder Doppelklick auf jarvis_oberflaeche.bat)

Wie das funktioniert:
- Dieses Programm startet einen kleinen Webserver NUR auf deinem PC (127.0.0.1).
- Die Oberfläche (oberflaeche/index.html) öffnet sich als eigenes Fenster und fragt
  jede Sekunde nach dem aktuellen Stand (Uhrzeit, CPU, Termine, Jarvis-Zustand ...).
- Im Hintergrund hört Jarvis wie gewohnt aufs Mikrofon.
"""

import json
import os
import platform
import queue
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import einstellungen
import stimme
import termine
from gehirn import Gehirn
from jarvis import env_datei_laden, ist_beenden
from werkzeuge import Werkzeugkasten

try:
    import psutil  # für CPU, RAM, Netz – optional
except ImportError:
    psutil = None

HTML_DATEI = Path(__file__).resolve().parent / "oberflaeche" / "index.html"
WERKZEUG_NAMEN = {
    "termin_eintragen": "Termin gespeichert", "termine_anzeigen": "Termine gelesen",
    "termin_loeschen": "Termin gelöscht", "hyperliquid_bericht": "Hyperliquid-Bericht geladen",
    "programm_oeffnen": "Programm geöffnet", "webseite_oeffnen": "Webseite geöffnet",
    "medien_steuern": "Medien gesteuert", "datei_suchen": "Dateien gesucht",
    "datei_oeffnen": "Datei geöffnet", "pc_sperren": "PC gesperrt",
}


# ---------------------------------------------------------------------------
# Gemeinsamer Zustand – alle Programmteile schreiben hier hinein
# ---------------------------------------------------------------------------

class Zustand:
    def __init__(self):
        self.sperre = threading.Lock()
        self.modus = "bereit"          # bereit | hoert | denkt | spricht
        self.mikro_an = True
        self.mikro_fehler = None
        self.log = deque(maxlen=80)     # Agent-Log
        self.dialog = deque(maxlen=30)  # Gespräch (Du / Jarvis)
        self.meldungen = deque(maxlen=40)  # Wächter
        self._meldung_id = 0

    def setze_modus(self, modus):
        with self.sperre:
            self.modus = modus

    def protokoll(self, text, art="info"):
        with self.sperre:
            self.log.append({"zeit": datetime.now().strftime("%H:%M:%S"), "text": text, "art": art})

    def sage(self, wer, text):
        with self.sperre:
            self.dialog.append({"zeit": datetime.now().strftime("%H:%M"), "wer": wer, "text": text})

    def melde(self, kategorie, titel, text=""):
        with self.sperre:
            self._meldung_id += 1
            self.meldungen.appendleft({"id": self._meldung_id, "kategorie": kategorie, "titel": titel,
                                       "text": text, "zeit": time.time()})

    def quittieren(self, meldung_id=None):
        with self.sperre:
            if meldung_id is None:
                self.meldungen.clear()
            else:
                self.meldungen = deque((m for m in self.meldungen if m["id"] != meldung_id), maxlen=40)


zustand = Zustand()
auftraege = queue.Queue()  # Fragen an Jarvis (getippt oder gesprochen)


# ---------------------------------------------------------------------------
# Hintergrund-Arbeiter
# ---------------------------------------------------------------------------

def denker(gehirn):
    """Beantwortet die Fragen nacheinander (damit nichts durcheinandergerät)."""
    while True:
        frage, quelle = auftraege.get()
        zustand.sage("du", frage)
        zustand.protokoll(f"Befehl ({quelle}): {frage}", "befehl")
        zustand.setze_modus("denkt")
        antwort = gehirn.frage(frage)
        zustand.sage("jarvis", antwort)
        zustand.protokoll("Antwort bereit", "ok")
        zustand.setze_modus("spricht")
        stimme.sprechen(antwort)
        zustand.setze_modus("bereit")


def lauscher():
    """Hört aufs Mikrofon und gibt erkannte Befehle an den Denker weiter."""
    try:
        ohr = stimme.Ohr()
    except Exception as fehler:
        zustand.mikro_fehler = f"Mikrofon nicht verfügbar: {fehler}"
        zustand.mikro_an = False
        zustand.protokoll(zustand.mikro_fehler, "fehler")
        return
    zustand.protokoll("Mikrofon bereit – sag „Jarvis“", "ok")
    letzte_antwort = 0.0
    while True:
        if not zustand.mikro_an or zustand.modus in ("denkt", "spricht"):
            if zustand.modus in ("denkt", "spricht"):
                letzte_antwort = time.time()
            time.sleep(0.3)
            continue
        text = ohr.hoeren(warten_sekunden=5)
        if not text or not zustand.mikro_an:
            continue
        gerufen, befehl = stimme.wake_wort_entfernen(text)
        im_gespraech = time.time() - letzte_antwort < einstellungen.NACHFRAGE_SEKUNDEN
        if not gerufen and not im_gespraech:
            continue
        if gerufen and not befehl:
            zustand.setze_modus("hoert")
            stimme.sprechen("Ja?")
            befehl = ohr.hoeren(warten_sekunden=6)
            zustand.setze_modus("bereit")
            if not befehl:
                continue
        if ist_beenden(befehl):
            zustand.protokoll("Beenden per Sprache – Fenster bitte schließen", "info")
            continue
        auftraege.put((befehl, "Sprache"))


def termin_waechter(kalender):
    while True:
        for e in kalender.faellige():
            meldung = termine.meldung_fuer(e)
            zustand.melde("termin", meldung, e["zeit"].replace("T", " "))
            zustand.protokoll(meldung, "termin")
            stimme.sprechen(meldung)
        time.sleep(15)


def markt_waechter():
    """Meldet große Tagesbewegungen der beobachteten Coins (einmal pro Tag und Coin)."""
    gemeldet = set()
    while True:
        try:
            for m in hole_maerkte():
                schluessel = (m["coin"], datetime.now().date())
                if abs(m["prozent"]) >= einstellungen.MARKT_ALARM_PROZENT and schluessel not in gemeldet:
                    gemeldet.add(schluessel)
                    pfeil = "▲" if m["prozent"] > 0 else "▼"
                    zustand.melde("markt", f"{m['coin']} {pfeil} {m['prozent']:+.1f} %",
                                  f"Kurs {m['preis']:,.2f} USD".replace(",", "X").replace(".", ",").replace("X", "."))
        except Exception:
            pass
        time.sleep(300)


# ---------------------------------------------------------------------------
# Daten für die Felder (mit kleinem Zwischenspeicher, damit wir APIs nicht überlasten)
# ---------------------------------------------------------------------------

_cache = {}


def zwischengespeichert(name, sekunden, funktion):
    eintrag = _cache.get(name)
    if eintrag and time.time() - eintrag[0] < sekunden:
        return eintrag[1]
    wert = funktion()
    _cache[name] = (time.time(), wert)
    return wert


def _json_holen(url, daten=None):
    anfrage = urllib.request.Request(
        url, data=json.dumps(daten).encode() if daten is not None else None,
        headers={"Content-Type": "application/json", "User-Agent": "jarvis-dashboard"})
    with urllib.request.urlopen(anfrage, timeout=15) as antwort:
        return json.loads(antwort.read())


WETTER_TEXT = {0: ("Klar", "sonne"), 1: ("Überwiegend klar", "sonne"), 2: ("Teilweise bewölkt", "wolke"),
               3: ("Bedeckt", "wolke"), 45: ("Nebel", "nebel"), 48: ("Nebel", "nebel"),
               51: ("Nieselregen", "regen"), 53: ("Nieselregen", "regen"), 55: ("Nieselregen", "regen"),
               61: ("Leichter Regen", "regen"), 63: ("Regen", "regen"), 65: ("Starker Regen", "regen"),
               71: ("Leichter Schnee", "schnee"), 73: ("Schnee", "schnee"), 75: ("Starker Schnee", "schnee"),
               80: ("Schauer", "regen"), 81: ("Schauer", "regen"), 82: ("Starke Schauer", "regen"),
               95: ("Gewitter", "gewitter"), 96: ("Gewitter", "gewitter"), 99: ("Gewitter", "gewitter")}


def hole_wetter():
    def laden():
        ort = urllib.parse.quote(einstellungen.WETTER_ORT)
        geo = _json_holen(f"https://geocoding-api.open-meteo.com/v1/search?name={ort}&count=1&language=de")
        if not geo.get("results"):
            return {"fehler": f"Ort „{einstellungen.WETTER_ORT}“ nicht gefunden"}
        g = geo["results"][0]
        w = _json_holen(
            "https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}&timezone=auto"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
            "&forecast_days=5".format(g["latitude"], g["longitude"]))
        c, d = w["current"], w["daily"]
        tage = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]
        return {
            "ort": f"{g['name']}, {g.get('country', '')}",
            "temp": round(c["temperature_2m"]), "gefuehlt": round(c["apparent_temperature"]),
            "feuchte": c["relative_humidity_2m"], "wind": round(c["wind_speed_10m"]),
            "text": WETTER_TEXT.get(c["weather_code"], ("–", "wolke"))[0],
            "symbol": WETTER_TEXT.get(c["weather_code"], ("–", "wolke"))[1],
            "aufgang": d["sunrise"][0][11:16], "untergang": d["sunset"][0][11:16],
            "tage": [{"tag": tage[datetime.fromisoformat(d["time"][i]).weekday()],
                      "max": round(d["temperature_2m_max"][i]), "min": round(d["temperature_2m_min"][i]),
                      "regen": d["precipitation_probability_max"][i],
                      "symbol": WETTER_TEXT.get(d["weather_code"][i], ("–", "wolke"))[1]}
                     for i in range(1, min(5, len(d["time"])))],
        }
    return zwischengespeichert("wetter", 600, laden)


def hole_maerkte():
    def laden():
        meta, kontexte = _json_holen("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
        namen = [a["name"] for a in meta["universe"]]
        ergebnis = []
        for coin in einstellungen.MARKT_COINS:
            if coin in namen:
                k = kontexte[namen.index(coin)]
                preis, vortag = float(k["markPx"]), float(k["prevDayPx"] or 0)
                ergebnis.append({"coin": coin, "preis": preis,
                                 "prozent": (preis / vortag - 1) * 100 if vortag else 0.0})
        return ergebnis
    return zwischengespeichert("maerkte", 30, laden)


def hole_briefing(werkzeugkasten):
    """Die 'Einigkeit'-Zeilen aus dem Hyperliquid-Tagesbericht."""
    def laden():
        text = werkzeugkasten.ausfuehren("hyperliquid_bericht", {})
        zeilen = text.splitlines()
        quelle = zeilen[0].strip("[]") if zeilen and zeilen[0].startswith("[") else ""
        titel = next((z.lstrip("# ") for z in zeilen if z.startswith("# ")), "")
        einig = [z[2:].replace("**", "") for z in zeilen if z.startswith(("- 🟢", "- 🔴"))]
        if not titel:
            return {"fehler": text[:300]}
        return {"titel": titel, "quelle": quelle, "einig": einig[:8]}
    return zwischengespeichert("briefing", 900, laden)


_netz_vorher = None


def hole_system():
    global _netz_vorher
    if psutil is None:
        return {"fehler": "psutil nicht installiert"}
    netz = psutil.net_io_counters()
    jetzt = time.time()
    rx = tx = 0.0
    if _netz_vorher:
        dauer = max(jetzt - _netz_vorher[0], 0.001)
        rx = (netz.bytes_recv - _netz_vorher[1]) / dauer / 1024
        tx = (netz.bytes_sent - _netz_vorher[2]) / dauer / 1024
    _netz_vorher = (jetzt, netz.bytes_recv, netz.bytes_sent)
    platte = psutil.disk_usage(os.path.abspath(os.sep))
    return {"cpu": psutil.cpu_percent(), "ram": psutil.virtual_memory().percent,
            "disk": platte.percent, "rx": round(rx, 1), "tx": round(tx, 1)}


# ---------------------------------------------------------------------------
# Der kleine Webserver
# ---------------------------------------------------------------------------

def baue_handler(kalender, werkzeugkasten):
    erlaubte_hosts = {f"127.0.0.1:{einstellungen.OBERFLAECHE_PORT}",
                      f"localhost:{einstellungen.OBERFLAECHE_PORT}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # keine Server-Meldungen im Fenster

        def _sicher(self):
            # Schutz: nur Anfragen an unsere eigene Adresse ...
            if self.headers.get("Host") not in erlaubte_hosts:
                self.send_error(403)
                return False
            # ... und Befehle nur von unserer eigenen Seite (fremde Webseiten können
            # diesen Header nicht mitschicken)
            if self.command == "POST" and self.headers.get("X-Jarvis") != "1":
                self.send_error(403)
                return False
            return True

        def _antwort(self, daten, status=200):
            inhalt = json.dumps(daten, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(inhalt)))
            self.end_headers()
            self.wfile.write(inhalt)

        def _sicher_laden(self, funktion):
            try:
                return funktion()
            except Exception as fehler:
                return {"fehler": f"nicht erreichbar ({type(fehler).__name__})"}

        def do_GET(self):
            if not self._sicher():
                return
            pfad = self.path.split("?")[0]
            if pfad == "/":
                inhalt = HTML_DATEI.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(inhalt)))
                self.end_headers()
                self.wfile.write(inhalt)
            elif pfad == "/api/zustand":
                jetzt = datetime.now()
                with zustand.sperre:
                    daten = {
                        "modus": zustand.modus, "mikro_an": zustand.mikro_an,
                        "mikro_fehler": zustand.mikro_fehler,
                        "log": list(zustand.log), "dialog": list(zustand.dialog),
                        "meldungen": list(zustand.meldungen),
                    }
                daten["termine"] = [e for e in kalender.auflisten(von=jetzt.strftime(termine.ZEITFORMAT))][:12]
                daten["system"] = self._sicher_laden(hole_system)
                daten["host"] = platform.node()
                daten["os"] = f"{platform.system()} {platform.release()}"
                self._antwort(daten)
            elif pfad == "/api/wetter":
                self._antwort(self._sicher_laden(hole_wetter))
            elif pfad == "/api/maerkte":
                self._antwort(self._sicher_laden(lambda: {"kurse": hole_maerkte()}))
            elif pfad == "/api/briefing":
                self._antwort(self._sicher_laden(lambda: hole_briefing(werkzeugkasten)))
            else:
                self.send_error(404)

        def do_POST(self):
            if not self._sicher():
                return
            laenge = int(self.headers.get("Content-Length", 0) or 0)
            try:
                daten = json.loads(self.rfile.read(min(laenge, 20000)) or b"{}")
            except json.JSONDecodeError:
                return self._antwort({"fehler": "ungültig"}, 400)
            if self.path == "/api/frage":
                text = str(daten.get("text", "")).strip()[:2000]
                if text:
                    auftraege.put((text, "Tastatur"))
                self._antwort({"ok": True})
            elif self.path == "/api/mikro":
                zustand.mikro_an = bool(daten.get("an")) and zustand.mikro_fehler is None
                zustand.protokoll("Mikrofon " + ("an" if zustand.mikro_an else "aus"))
                self._antwort({"ok": True, "mikro_an": zustand.mikro_an})
            elif self.path == "/api/quittieren":
                zustand.quittieren(daten.get("id"))
                self._antwort({"ok": True})
            else:
                self.send_error(404)

    return Handler


def fenster_oeffnen(url):
    """Öffnet die Oberfläche als eigenes Fenster (Edge-App-Modus), sonst im Browser."""
    if platform.system() == "Windows":
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "msedge", f"--app={url}"])
            return
        except Exception:
            pass
    webbrowser.open(url)


def main():
    env_datei_laden()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Es fehlt der API-Schlüssel. Lege die Datei jarvis/.env an (siehe README).")
        sys.exit(1)

    kalender = termine.Terminkalender(einstellungen.TERMINE_DATEI)
    werkzeugkasten = Werkzeugkasten(kalender)
    gehirn = Gehirn(werkzeugkasten, beobachter=lambda name, eingaben: zustand.protokoll(
        WERKZEUG_NAMEN.get(name, name) + (f": {next(iter(eingaben.values()))}" if eingaben else ""),
        "werkzeug"))

    ohne_mikro = "--ohne-mikro" in sys.argv
    threading.Thread(target=denker, args=(gehirn,), daemon=True).start()
    threading.Thread(target=termin_waechter, args=(kalender,), daemon=True).start()
    threading.Thread(target=markt_waechter, daemon=True).start()
    if ohne_mikro:
        zustand.mikro_an = False
        zustand.mikro_fehler = "Mikrofon beim Start ausgeschaltet"
    else:
        threading.Thread(target=lauscher, daemon=True).start()

    port = einstellungen.OBERFLAECHE_PORT
    server = ThreadingHTTPServer(("127.0.0.1", port), baue_handler(kalender, werkzeugkasten))
    url = f"http://127.0.0.1:{port}/"
    begruessung = termine.tagesueberblick(kalender)
    zustand.protokoll("System gestartet", "ok")
    zustand.sage("jarvis", begruessung)
    print(f"Jarvis-Oberfläche läuft: {url}  (Fenster schließen + Strg+C zum Beenden)")
    if "--kein-fenster" not in sys.argv:
        fenster_oeffnen(url)
    threading.Thread(target=stimme.sprechen, args=(begruessung,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
