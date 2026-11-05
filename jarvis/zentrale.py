"""
JARVIS TRADING-ZENTRALE

Starten:  python zentrale.py   (oder Doppelklick auf jarvis_zentrale.bat)

Was hier passiert:
- Ein kleiner Webserver NUR auf deinem PC (127.0.0.1) liefert die Zentrale (zentrale/index.html)
  und alle Daten: Konto, Watchlist, Setups, TradingView-Ratings, News, Alarme, Tagebuch …
- Die Zentrale öffnet sich als eigenes Fenster. In der Mitte läuft der echte TradingView-Chart.
- Jarvis hört aufs Mikrofon, kann den Chart umschalten ("Jarvis, zeig mir Gold auf H1") und
  warnt dich von selbst: vor wichtigen News, vor dem FTMO-Tageslimit und abends vor offenen Positionen.
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
import webbrowser
from collections import deque
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import einstellungen
import stimme
import termine
import vollzugriff
from gehirn import Gehirn
from jarvis import env_datei_laden, ist_beenden
from werkzeuge import Werkzeugkasten

ORDNER = Path(__file__).resolve().parent
SEITEN = {
    "/": ORDNER / "zentrale" / "index.html",
    "/trading": ORDNER / "zentrale" / "index.html",
    "/vendor/lightweight-charts.js": ORDNER / "oberflaeche" / "vendor" / "lightweight-charts.js",
}
WERKZEUG_NAMEN = {
    "termin_eintragen": "Termin gespeichert", "termine_anzeigen": "Termine gelesen",
    "termin_loeschen": "Termin gelöscht", "hyperliquid_bericht": "Hyperliquid-Bericht",
    "programm_oeffnen": "Programm geöffnet", "webseite_oeffnen": "Webseite geöffnet",
    "programm_schliessen": "Programm geschlossen", "youtube_abspielen": "YouTube",
    "spotify_suchen": "Spotify", "markt_analyse": "Marktanalyse", "maerkte_ueberblick": "Marktüberblick",
    "konto_status": "Kontostand", "befehl_ausfuehren": "Befehl", "werkzeug_erstellen": "Neues Werkzeug",
    "jarvis_aktualisieren": "Update", "mt5_zugang_speichern": "MT5-Zugang",
    "tradingview_analyse": "TradingView-Analyse", "setup_scanner": "Setup-Scanner",
    "positionsgroesse_berechnen": "Positionsgröße", "alarm_setzen": "Alarm gesetzt",
    "alarme_verwalten": "Alarme", "wirtschaftskalender": "Wirtschaftskalender",
    "chart_zeigen": "Chart", "bildschirm_ansehen": "Schaut auf den Bildschirm",
    "tagebuch_eintragen": "Tagebuch", "tagebuch_auswertung": "Tagebuch-Auswertung",
    "an_claude_melden": "An Claude gemeldet", "neuigkeiten": "Neuigkeiten",
    "trader_status": "Roboter-Status", "trader_steuern": "Roboter gesteuert", "backtest_starten": "Backtest",
    "trading_tagesbericht": "Tagesbericht",
    "medien_steuern": "Medien", "datei_suchen": "Dateisuche", "datei_oeffnen": "Datei geöffnet",
    "pc_sperren": "PC gesperrt",
}


# ---------------------------------------------------------------------------
# Gemeinsamer Zustand
# ---------------------------------------------------------------------------

class Zustand:
    def __init__(self):
        self.sperre = threading.Lock()
        self.modus = "bereit"            # bereit | hoert | denkt | spricht | wartet
        self.mikro_an = True
        self.mikro_fehler = None
        self.log = deque(maxlen=80)
        self.dialog = deque(maxlen=40)
        self.meldungen = deque(maxlen=40)
        self.chart_befehl = None          # {"id", "symbol", "zeitrahmen"} – Jarvis schaltet den Chart um
        self._id = 0

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
            self._id += 1
            self.meldungen.appendleft({"id": self._id, "kategorie": kategorie, "titel": titel,
                                       "text": text, "zeit": time.time()})

    def quittieren(self, meldung_id=None):
        with self.sperre:
            if meldung_id is None:
                self.meldungen.clear()
            else:
                self.meldungen = deque((m for m in self.meldungen if m["id"] != meldung_id), maxlen=40)

    def chart(self, symbol, zeitrahmen):
        with self.sperre:
            self._id += 1
            self.chart_befehl = {"id": self._id, "symbol": symbol, "zeitrahmen": zeitrahmen}


zustand = Zustand()
auftraege = queue.Queue()


class Freigabe:
    """Offene Frage "Darf ich das?" – beantwortet per Klick oder per Stimme."""

    def __init__(self):
        self.sperre = threading.Lock()
        self.anfrage = None
        self._ereignis = threading.Event()
        self._antwort = False
        self._zaehler = 0

    def fragen(self, art, beschreibung, details):
        with self.sperre:
            self._zaehler += 1
            self.anfrage = {"id": self._zaehler, "art": art, "beschreibung": beschreibung,
                            "details": details[:20000]}
            self._ereignis.clear()
            self._antwort = False
        vorher = zustand.modus
        zustand.setze_modus("wartet")
        zustand.protokoll(f"Wartet auf Freigabe: {beschreibung}", "warnung")
        threading.Thread(target=stimme.sprechen, daemon=True,
                         args=(f"Ich brauche deine Freigabe: {beschreibung}. Soll ich?",)).start()
        self._ereignis.wait(einstellungen.BESTAETIGUNG_SEKUNDEN)
        with self.sperre:
            ok, self.anfrage = self._antwort, None
        zustand.protokoll("Freigabe erteilt" if ok else "Freigabe abgelehnt", "ok" if ok else "fehler")
        zustand.setze_modus(vorher)
        return ok

    def antworten(self, anfrage_id, ja):
        with self.sperre:
            if self.anfrage and (anfrage_id is None or self.anfrage["id"] == anfrage_id):
                self._antwort = bool(ja)
                self._ereignis.set()


freigabe = Freigabe()
backtest_stand = {"laeuft": False, "text": ""}


def melden(text, kategorie="alarm", sprechen=True):
    """Jarvis meldet sich von selbst: Meldung in der Zentrale + Stimme."""
    zustand.melde(kategorie, text)
    zustand.protokoll(text, "warnung")
    if sprechen:
        stimme.sprechen(text)


# ---------------------------------------------------------------------------
# Zwischenspeicher, damit Internet-Quellen nicht überlastet werden
# ---------------------------------------------------------------------------

_cache = {}
_cache_sperre = threading.Lock()


def zwischengespeichert(name, sekunden, funktion):
    with _cache_sperre:
        eintrag = _cache.get(name)
        if eintrag and time.time() - eintrag[0] < sekunden:
            return eintrag[1]
    wert = funktion()
    with _cache_sperre:
        _cache[name] = (time.time(), wert)
    return wert


# ---------------------------------------------------------------------------
# Daten für die Felder
# ---------------------------------------------------------------------------

def kalender_daten():
    """Wichtige und mittlere News heute und morgen, mit Zeitstempel für den Countdown."""
    from trading import kalender

    def laden():
        jetzt = datetime.now(timezone.utc)
        anfang = jetzt.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        liste = kalender.termine(kalender.laden(), anfang, anfang + timedelta(days=2), nur_wichtig=False)
        return [{"zeit": int(e["zeit"].timestamp()), "titel": e["titel"], "waehrung": e["waehrung"],
                 "wichtig": e["wichtig"], "prognose": e["prognose"], "vorher": e["vorher"]}
                for e in liste if e["wichtig"] in ("HOCH", "mittel")]
    return {"termine": zwischengespeichert("kalender", 900, laden),
            "waehrungen": einstellungen.NEWS_WAEHRUNGEN}


def tradingview_daten(symbol):
    from trading import kursquellen, tradingview
    ticker = kursquellen.tradingview_kuerzel(symbol)
    if not ticker:
        return {"fehler": f"Kein TradingView-Kürzel für {symbol}"}
    e = zwischengespeichert(f"tv:{ticker}", 60, lambda: tradingview.analyse(ticker))
    if not e:
        return {"fehler": f"TradingView kennt {ticker} nicht"}
    return {"ticker": ticker, "tag": e["tag"],
            "zeitrahmen": {tf: {"gesamt": w["Recommend.All"], "ma": w["Recommend.MA"], "osz": w["Recommend.Other"],
                                "text": tradingview.bewertung(w["Recommend.All"]), "rsi": w["RSI"], "adx": w["ADX"]}
                           for tf, w in e["zeitrahmen"].items()}}


def briefing_daten(werkzeugkasten):
    def laden():
        text = werkzeugkasten.ausfuehren("hyperliquid_bericht", {})
        zeilen = text.splitlines()
        titel = next((z.lstrip("# ") for z in zeilen if z.startswith("# ")), "")
        einig = [z[2:].replace("**", "") for z in zeilen if z.startswith(("- 🟢", "- 🔴"))]
        if not titel:
            return {"fehler": text[:300]}
        return {"titel": titel, "einig": einig[:8]}
    return zwischengespeichert("briefing", 900, laden)


def krypto_daten():
    """Live-Kurse der Krypto-Coins für die Laufleiste (Hyperliquid)."""
    import urllib.request

    def laden():
        anfrage = urllib.request.Request("https://api.hyperliquid.xyz/info",
                                         data=json.dumps({"type": "metaAndAssetCtxs"}).encode(),
                                         headers={"Content-Type": "application/json", "User-Agent": "jarvis"})
        with urllib.request.urlopen(anfrage, timeout=15) as antwort:
            meta, kontexte = json.loads(antwort.read())
        namen = [a["name"] for a in meta["universe"]]
        ergebnis = []
        for coin in einstellungen.MARKT_COINS:
            if coin in namen:
                k = kontexte[namen.index(coin)]
                preis, vortag = float(k["markPx"]), float(k["prevDayPx"] or 0)
                ergebnis.append({"coin": coin, "preis": preis,
                                 "prozent": (preis / vortag - 1) * 100 if vortag else 0.0})
        return ergebnis
    return {"kurse": zwischengespeichert("krypto", 20, laden)}


# ---------------------------------------------------------------------------
# Hintergrund-Arbeiter
# ---------------------------------------------------------------------------

def denker(gehirn):
    while True:
        frage, quelle = auftraege.get()
        zustand.sage("du", frage)
        zustand.protokoll(f"Befehl ({quelle}): {frage}", "befehl")
        zustand.setze_modus("denkt")
        antwort = gehirn.frage(frage)
        zustand.sage("jarvis", antwort)
        zustand.setze_modus("spricht")
        stimme.sprechen(antwort)
        zustand.setze_modus("bereit")


def lauscher():
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
        if freigabe.anfrage and zustand.mikro_an:
            antwort = ohr.hoeren(warten_sekunden=5, max_satz_sekunden=5)
            if antwort:
                rest = stimme.wake_wort_entfernen(antwort)[1].lower()
                if vollzugriff.ist_ja(rest):
                    freigabe.antworten(None, True)
                elif any(w in rest for w in ("nein", "stopp", "stop", "abbrechen", "nicht")):
                    freigabe.antworten(None, False)
            continue
        if not zustand.mikro_an or zustand.modus in ("denkt", "spricht", "wartet"):
            if zustand.modus in ("denkt", "spricht"):
                letzte_antwort = time.time()
            time.sleep(0.3)
            continue
        text = ohr.hoeren(warten_sekunden=5)
        if not text or not zustand.mikro_an:
            continue
        gerufen, befehl = stimme.wake_wort_entfernen(text)
        if not gerufen and time.time() - letzte_antwort >= einstellungen.NACHFRAGE_SEKUNDEN:
            continue
        if gerufen and not befehl:
            zustand.setze_modus("hoert")
            stimme.sprechen("Ja?")
            befehl = ohr.hoeren(warten_sekunden=6)
            zustand.setze_modus("bereit")
            if not befehl:
                continue
        if ist_beenden(befehl):
            continue
        auftraege.put((befehl, "Sprache"))


def termin_waechter(kalender):
    while True:
        for e in kalender.faellige():
            text = termine.meldung_fuer(e)
            zustand.melde("termin", text, e["zeit"].replace("T", " "))
            stimme.sprechen(text)
        time.sleep(15)


def news_pruefen(termine_liste, jetzt, bereits_gemeldet, minuten, waehrungen):
    """Gibt Warntexte für wichtige News zurück, die in den nächsten `minuten` kommen."""
    texte = []
    for e in termine_liste:
        bis = (e["zeit"] - jetzt) / 60
        schluessel = (e["zeit"], e["titel"])
        if (e["wichtig"] == "HOCH" and e["waehrung"] in waehrungen and 0 <= bis <= minuten
                and schluessel not in bereits_gemeldet):
            bereits_gemeldet.add(schluessel)
            texte.append(f"Achtung, in {max(round(bis), 1)} Minuten kommen wichtige News: "
                         f"{e['waehrung']} {e['titel']}. Vorsicht mit offenen Positionen und neuen Einstiegen.")
    return texte


def news_waechter():
    if not einstellungen.NEWS_WARNUNG_MINUTEN:
        return
    gemeldet = set()
    while True:
        try:
            for text in news_pruefen(kalender_daten()["termine"], time.time(), gemeldet,
                                     einstellungen.NEWS_WARNUNG_MINUTEN, einstellungen.NEWS_WAEHRUNGEN):
                melden(text, "news")
        except Exception:
            pass
        time.sleep(60)


def konto_waechter():
    """FTMO-Ampel beobachten (nur mit MT5) und abends an offene Positionen erinnern."""
    from trading import marktdaten
    letzte_ampel = None
    erinnert_am = None
    while True:
        try:
            d = marktdaten.konto_daten()
            ampel = d["pruefung"]["ampel"]
            if ampel != letzte_ampel and letzte_ampel is not None and ampel in ("gelb", "rot"):
                rest = d["pruefung"]["rest_tagesverlust_sicher"]
                melden(f"FTMO-Ampel {ampel.upper()}: Noch {rest:.0f} bis zu deinem Tageslimit. "
                       + ("Für heute bitte keine neuen Trades mehr." if ampel == "rot"
                          else "Bitte kleiner handeln."), "konto")
            letzte_ampel = ampel
            jetzt = datetime.now()
            if (einstellungen.TAGESENDE_ERINNERUNG and d["konto"]["positionen"]
                    and jetzt.strftime("%H:%M") >= einstellungen.TAGESENDE_ERINNERUNG
                    and erinnert_am != jetzt.date()):
                erinnert_am = jetzt.date()
                melden(f"Es ist {jetzt:%H:%M}. Du hast noch {len(d['konto']['positionen'])} offene Position(en). "
                       "Als Daytrader solltest du sie vor Handelsschluss schließen.", "konto")
        except Exception:
            pass
        time.sleep(30)


def update_waechter():
    """Prüft beim Start und dann alle 6 Stunden, ob Claude ein Update veröffentlicht hat."""
    import sync
    gemeldet = set()
    time.sleep(30)
    while True:
        try:
            neu = [e for e in sync.update_pruefen() if e["kopf"] not in gemeldet]
            if neu:
                gemeldet.update(e["kopf"] for e in neu)
                titel = "; ".join(e["kopf"].split("·", 1)[-1].strip() for e in neu[:3])
                melden(f"Es gibt ein neues Jarvis-Update: {titel}. Sag „Jarvis, aktualisiere dich“, "
                       "um es zu installieren.", "update")
        except Exception:
            pass
        time.sleep(6 * 3600)


def krypto_waechter():
    gemeldet = set()
    while True:
        try:
            for m in krypto_daten()["kurse"]:
                schluessel = (m["coin"], datetime.now().date())
                if abs(m["prozent"]) >= einstellungen.MARKT_ALARM_PROZENT and schluessel not in gemeldet:
                    gemeldet.add(schluessel)
                    zustand.melde("markt", f"{m['coin']} {'▲' if m['prozent'] > 0 else '▼'} {m['prozent']:+.1f} %",
                                  f"Kurs {m['preis']:.2f} USD")
        except Exception:
            pass
        time.sleep(300)


# ---------------------------------------------------------------------------
# Webserver
# ---------------------------------------------------------------------------

def baue_handler(kalender, werkzeugkasten):
    from trading import marktdaten
    erlaubte_hosts = {f"127.0.0.1:{einstellungen.OBERFLAECHE_PORT}", f"localhost:{einstellungen.OBERFLAECHE_PORT}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _sicher(self):
            if self.headers.get("Host") not in erlaubte_hosts:
                self.send_error(403)
                return False
            if self.command == "POST" and self.headers.get("X-Jarvis") != "1":
                self.send_error(403)  # fremde Webseiten können diesen Header nicht senden
                return False
            return True

        def _antwort(self, daten, status=200):
            inhalt = json.dumps(daten, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(inhalt)))
            self.end_headers()
            self.wfile.write(inhalt)

        def _versuche(self, funktion):
            try:
                return funktion()
            except Exception as fehler:
                return {"fehler": str(fehler)[:300] or type(fehler).__name__}

        def do_GET(self):
            if not self._sicher():
                return
            pfad = self.path.split("?")[0]
            p = dict(urllib.parse.parse_qsl(self.path.partition("?")[2]))
            symbol = p.get("symbol") or einstellungen.TRADING_MAERKTE[0]
            tf = (p.get("tf") or einstellungen.TRADING_ZEITRAHMEN).upper()
            if pfad in SEITEN:
                datei = SEITEN[pfad]
                if not datei.exists():
                    return self.send_error(404)
                inhalt = datei.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript; charset=utf-8" if datei.suffix == ".js"
                                 else "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(inhalt)))
                self.end_headers()
                self.wfile.write(inhalt)
            elif pfad == "/api/zustand":
                with zustand.sperre:
                    daten = {"modus": zustand.modus, "mikro_an": zustand.mikro_an,
                             "mikro_fehler": zustand.mikro_fehler, "log": list(zustand.log),
                             "dialog": list(zustand.dialog), "meldungen": list(zustand.meldungen),
                             "chart_befehl": zustand.chart_befehl}
                daten["freigabe"] = freigabe.anfrage
                daten["termine"] = kalender.auflisten(von=datetime.now().strftime(termine.ZEITFORMAT))[:8]
                self._antwort(daten)
            elif pfad == "/api/einstellungen":
                from trading import kursquellen
                self._antwort({"maerkte": einstellungen.TRADING_MAERKTE, "zeitrahmen": einstellungen.TRADING_ZEITRAHMEN,
                               "risiko": einstellungen.RISIKO_STANDARD_PROZENT, "anrede": einstellungen.ANREDE,
                               "farbschema": getattr(einstellungen, "FARBSCHEMA", "rot"),
                               "tradingview": {m: kursquellen.tradingview_kuerzel(m) for m in einstellungen.TRADING_MAERKTE
                                               if kursquellen.tradingview_kuerzel(m)},
                               "alle_tradingview": {n: tv for n, (_, tv) in kursquellen.SYMBOLE.items()}})
            elif pfad == "/api/chart":
                self._antwort(self._versuche(lambda: marktdaten.chart_daten(symbol, tf)))
            elif pfad == "/api/konto":
                self._antwort(self._versuche(marktdaten.konto_daten))
            elif pfad == "/api/ueberblick":
                self._antwort(self._versuche(lambda: zwischengespeichert(
                    "ueberblick", 20, lambda: {"maerkte": marktdaten.ueberblick_daten()})))
            elif pfad == "/api/setups":
                self._antwort(self._versuche(lambda: zwischengespeichert(
                    f"setups:{tf}", 120, lambda: {"zeitrahmen": tf, "zeit": time.time(),
                                                   "maerkte": marktdaten.setups_daten(tf)})))
            elif pfad == "/api/tradingview":
                self._antwort(self._versuche(lambda: tradingview_daten(symbol)))
            elif pfad == "/api/kalender":
                self._antwort(self._versuche(kalender_daten))
            elif pfad == "/api/krypto":
                self._antwort(self._versuche(krypto_daten))
            elif pfad == "/api/briefing":
                self._antwort(self._versuche(lambda: briefing_daten(werkzeugkasten)))
            elif pfad == "/api/alarme":
                system = werkzeugkasten._alarme()
                self._antwort({"alarme": [dict(a, text=system.beschreibung(a)) for a in system.aktive()]})
            elif pfad == "/api/positionsgroesse":
                self._antwort(self._versuche(lambda: marktdaten.positions_rechner(
                    symbol, float(p["einstieg"]), float(p["stop"]), float(p.get("risiko") or
                                                                           einstellungen.RISIKO_STANDARD_PROZENT))))
            elif pfad == "/api/trader":
                engine = werkzeugkasten.trader
                self._antwort(engine.status_daten() if engine else {"fehler": "Trading-Roboter ist ausgeschaltet (TRADER_AKTIV)"})
            elif pfad == "/api/backtest":
                self._antwort(backtest_stand)
            elif pfad == "/api/tagebuch":
                tb = werkzeugkasten._tagebuch()
                self._antwort({"auswertung": tb.auswertung(int(p.get("tage") or 30)),
                               "eintraege": tb.liste(int(p.get("tage") or 30))[-20:][::-1]})
            else:
                self.send_error(404)

        def do_POST(self):
            if not self._sicher():
                return
            laenge = int(self.headers.get("Content-Length", 0) or 0)
            try:
                d = json.loads(self.rfile.read(min(laenge, 20000)) or b"{}")
            except json.JSONDecodeError:
                return self._antwort({"fehler": "ungültig"}, 400)
            if self.path == "/api/frage":
                text = str(d.get("text", "")).strip()[:2000]
                if text:
                    auftraege.put((text, "Tastatur"))
                self._antwort({"ok": True})
            elif self.path == "/api/mikro":
                zustand.mikro_an = bool(d.get("an")) and zustand.mikro_fehler is None
                self._antwort({"ok": True, "mikro_an": zustand.mikro_an})
            elif self.path == "/api/trader":
                engine = werkzeugkasten.trader
                aktion = d.get("aktion")
                if engine is None or aktion not in ("pause", "fortsetzen", "notaus", "zuruecksetzen"):
                    return self._antwort({"fehler": "nicht möglich"}, 400)
                text = engine.steuern(aktion)
                zustand.protokoll(f"Trader: {text}", "warnung" if aktion == "notaus" else "info")
                self._antwort({"ok": True, "text": text})
            elif self.path == "/api/backtest":
                if backtest_stand.get("laeuft"):
                    return self._antwort({"fehler": "Es läuft schon ein Backtest."})
                symbol = str(d.get("symbol") or "").upper() or None
                backtest_stand.update({"laeuft": True, "symbol": symbol or "alle", "text": "", "start": time.time()})

                def rechnen():
                    try:
                        backtest_stand["text"] = werkzeugkasten.ausfuehren("backtest_starten", {"symbol": symbol} if symbol else {})
                    except Exception as fehler:
                        backtest_stand["text"] = f"Backtest fehlgeschlagen: {fehler}"
                    backtest_stand["laeuft"] = False
                    backtest_stand["fertig"] = time.time()
                threading.Thread(target=rechnen, daemon=True).start()
                self._antwort({"ok": True})
            elif self.path == "/api/stumm":
                self._antwort({"ok": stimme.stoppen()})
            elif self.path == "/api/freigabe":
                freigabe.antworten(d.get("id"), d.get("ja"))
                self._antwort({"ok": True})
            elif self.path == "/api/quittieren":
                zustand.quittieren(d.get("id"))
                self._antwort({"ok": True})
            elif self.path == "/api/alarm":
                self._antwort(self._versuche(lambda: {"alarm": werkzeugkasten._alarme().hinzufuegen(
                    d["symbol"], d["art"], None if d.get("wert") in (None, "") else float(d["wert"]),
                    d.get("zeitrahmen") or "M15")}))
            elif self.path == "/api/alarm_loeschen":
                self._antwort({"ok": werkzeugkasten._alarme().loeschen(d["id"])})
            elif self.path == "/api/tagebuch":
                zahl = lambda k: None if d.get(k) in (None, "") else float(d[k])
                self._antwort(self._versuche(lambda: {"eintrag": werkzeugkasten._tagebuch().eintragen(
                    d["symbol"], d["richtung"], zahl("einstieg"), zahl("stop"), zahl("ausstieg"), zahl("gewinn"),
                    d.get("notiz", ""), d.get("setup", ""))}))
            elif self.path == "/api/tagebuch_loeschen":
                self._antwort({"ok": werkzeugkasten._tagebuch().loeschen(d["id"])})
            else:
                self.send_error(404)

    return Handler


def fenster_oeffnen(url):
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
    werkzeugkasten = Werkzeugkasten(kalender, bestaetigen=freigabe.fragen)
    werkzeugkasten.melden = lambda text: melden(text, "alarm")

    def ui_befehl(befehl):
        if befehl.get("aktion") == "chart":
            zustand.chart(befehl["symbol"], befehl.get("zeitrahmen") or einstellungen.TRADING_ZEITRAHMEN)
            return True
        return False
    werkzeugkasten.ui_befehl = ui_befehl
    werkzeugkasten.alarme_starten()

    if getattr(einstellungen, "TRADER_AKTIV", False):
        from trader.engine import TradingEngine
        from trading import marktdaten

        def wichtige_news():
            return [t for t in kalender_daten()["termine"] if t["wichtig"] == "HOCH"]
        engine = TradingEngine(einstellungen, marktdaten.kerzen_holen, melden=lambda text: melden(text, "trader"),
                               news=wichtige_news)
        werkzeugkasten.trader = engine
        engine.starten()
        zustand.protokoll(f"Trading-Roboter gestartet (Stufe {engine.stufe}, PAPER, Status {engine.status})", "ok")

    gehirn = Gehirn(werkzeugkasten, beobachter=lambda name, eingaben: zustand.protokoll(
        WERKZEUG_NAMEN.get(name, name) + (f": {next(iter(eingaben.values()))}" if eingaben else ""), "werkzeug"))

    for ziel in (lambda: denker(gehirn), lambda: termin_waechter(kalender), news_waechter,
                 konto_waechter, krypto_waechter, update_waechter):
        threading.Thread(target=ziel, daemon=True).start()
    if "--ohne-mikro" in sys.argv:
        zustand.mikro_an = False
        zustand.mikro_fehler = "Mikrofon beim Start ausgeschaltet"
    else:
        threading.Thread(target=lauscher, daemon=True).start()

    port = einstellungen.OBERFLAECHE_PORT
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), baue_handler(kalender, werkzeugkasten))
    except OSError:
        print(f"Port {port} ist belegt – läuft Jarvis schon? Bitte das andere Jarvis-Fenster schließen.")
        sys.exit(1)
    url = f"http://127.0.0.1:{port}/"
    begruessung = termine.tagesueberblick(kalender)
    zustand.sage("jarvis", begruessung)
    zustand.protokoll("Trading-Zentrale gestartet", "ok")
    print(f"Jarvis Trading-Zentrale läuft: {url}")
    if "--kein-fenster" not in sys.argv:
        fenster_oeffnen(url)
    threading.Thread(target=stimme.sprechen, args=(begruessung,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
