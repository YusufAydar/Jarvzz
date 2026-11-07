"""
Die Trading-Engine: schaut jede Minute auf die Märkte und entscheidet BUY / SELL / HOLD / WAIT.

Ablauf pro Markt und Durchgang:
  1. Kerzen holen (MT5, sonst Hyperliquid/Yahoo) und die DATENQUALITÄT prüfen (zu alt -> nicht handeln)
  2. Offene Paper-Positionen verwalten: Stop-Loss / Take-Profit / Tagesende
  3. Nur bei einer NEU abgeschlossenen Kerze: Strategie bewerten -> Signal mit Confidence
  4. Risiko-Engine prüft alle Grenzen -> erst dann eine Paper-Position eröffnen
  5. Jede Entscheidung wird mit Begründung gespeichert (daten/trader_entscheidungen.jsonl)

Stufe 0 = nur Signale melden, Stufe 1 = Paper-Trading. Echte Orders gibt es in dieser Version NICHT.
Bei technischen Fehlern pausiert die Engine sich selbst; bei zu großem Drawdown sperrt sie sich.
"""

import json
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from trader import bericht, paper, risiko, strategien

DATEN_ALTER_MAX = 2 * 15 * 60 + 300  # M15: älter als ~35 Minuten = veraltet


class TradingEngine:
    def __init__(self, e, kerzen_holen, melden=None, news=None, ordner=None):
        self.e = e
        self.regeln = risiko.Regeln(e)
        self.kerzen_holen = kerzen_holen        # Funktion(symbol, zeitrahmen, anzahl) -> (name, stellen, quelle, kerzen)
        self.melden = melden or (lambda text: None)
        self.news = news or (lambda: [])        # Funktion -> Liste wichtiger Termine
        self.ordner = Path(ordner or e.DATEN_ORDNER)
        self.konto = paper.PaperKonto(e.TRADER_KONTO_START, self.ordner / "paper_konto.json")
        self.entscheidungen = deque(maxlen=200)
        self.letzte_kerze, self.preise, self.quellen, self.markt_info = {}, {}, {}, {}
        self.fehler_in_folge = 0
        self.letzter_durchgang = None
        self.bericht_tag = None
        self._sperre = threading.RLock()
        self._status_datei = self.ordner / "trader_status.json"
        try:
            gespeichert = json.loads(self._status_datei.read_text(encoding="utf-8"))
        except Exception:
            gespeichert = {}
        self.status = gespeichert.get("status", "aktiv")
        self.status_grund = gespeichert.get("grund", "")
        self.stufe = min(int(e.TRADER_STUFE), 1)   # Stufe 2/3 (echtes Geld) ist noch nicht freigeschaltet

    # ---------- Zustand ----------

    def _status_setzen(self, status, grund=""):
        self.status, self.status_grund = status, grund
        self.ordner.mkdir(parents=True, exist_ok=True)
        self._status_datei.write_text(json.dumps({"status": status, "grund": grund}, ensure_ascii=False),
                                      encoding="utf-8")

    def _protokoll(self, symbol, aktion, gruende, confidence=None, teile=None, preis=None):
        eintrag = {"zeit": time.time(), "symbol": symbol, "aktion": aktion, "confidence": confidence,
                   "gruende": gruende, "teile": teile or {}, "preis": preis}
        self.entscheidungen.appendleft(eintrag)
        try:
            self.ordner.mkdir(parents=True, exist_ok=True)
            with open(self.ordner / "trader_entscheidungen.jsonl", "a", encoding="utf-8") as datei:
                datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return eintrag

    # ---------- Steuerung ----------

    def steuern(self, aktion):
        with self._sperre:
            if aktion == "pause":
                self._status_setzen("pausiert", "von dir pausiert")
                return "Roboter pausiert: keine neuen Trades. Offene Positionen behalten ihren Stop-Loss."
            if aktion == "fortsetzen":
                if self.status == "gesperrt":
                    return "Der Roboter ist wegen zu großem Drawdown gesperrt. Erst 'zuruecksetzen' (nach Prüfung)."
                self._status_setzen("aktiv")
                return "Roboter läuft wieder."
            if aktion == "notaus":
                geschlossen = self.konto.alle_schliessen(self.preise, time.time(), "NOT-AUS")
                self._status_setzen("notaus", "Not-Aus gedrückt")
                return f"NOT-AUS: {len(geschlossen)} Paper-Position(en) geschlossen, keine neuen Trades."
            if aktion == "zuruecksetzen":
                self.konto.zuruecksetzen(self.e.TRADER_KONTO_START)
                self._status_setzen("aktiv")
                return f"Paper-Konto auf {self.e.TRADER_KONTO_START} $ zurückgesetzt, Roboter läuft."
        return f"Unbekannte Aktion: {aktion}"

    # ---------- Ein Durchgang ----------

    def schritt(self, jetzt=None):
        jetzt = jetzt or time.time()
        with self._sperre:
            self.konto.tag_pruefen(jetzt, self.preise)
            self._tagesende(jetzt)
            for symbol in self.e.TRADER_MAERKTE:
                self._markt(symbol, jetzt)
            self._drawdown_pruefen()
            self.letzter_durchgang = jetzt

    def _tagesende(self, jetzt):
        t = risiko.wien_zeit(jetzt)
        hm = t.strftime("%H:%M")
        if self.konto.zustand["offene"] and (t.weekday() >= 5 or hm >= self.regeln.schliessen_um):
            for trade in self.konto.alle_schliessen(self.preise, jetzt, "Tagesende (Daytrading)"):
                self._trade_gemeldet(trade)
        tag = t.strftime("%Y-%m-%d")
        if hm >= self.regeln.handelszeit[1] and self.bericht_tag != tag and t.weekday() < 5:
            self.bericht_tag = tag
            try:
                text = bericht.tagesbericht(self, tag)
                ziel = self.ordner / "trading_berichte" / f"{tag}.md"
                ziel.parent.mkdir(parents=True, exist_ok=True)
                ziel.write_text(text, encoding="utf-8")
                kurz = bericht.kurzfassung(self, tag)
                self.melden(f"Mein Trading-Tagesbericht ist fertig. {kurz}")
            except Exception as fehler:
                print(f"[Tagesbericht fehlgeschlagen: {fehler}]")

    def _markt(self, symbol, jetzt):
        try:
            name, stellen, quelle, kerzen = self.kerzen_holen(symbol, "M15", 400)
            h1 = self.kerzen_holen(symbol, "H1", 250)[3]
        except Exception as fehler:
            self.markt_info[symbol] = {"fehler": f"keine Kursdaten ({fehler})"[:120]}
            return
        if len(kerzen) < 120 or len(h1) < 70:
            self.markt_info[symbol] = {"fehler": "zu wenig Kursdaten"}
            return
        preis = kerzen[-1]["close"]
        self.preise[symbol], self.quellen[symbol] = preis, quelle
        alter = jetzt - kerzen[-1]["zeit"]
        veraltet = alter > DATEN_ALTER_MAX
        self.markt_info[symbol] = {"name": name, "preis": preis, "stellen": stellen, "quelle": quelle,
                                   "datenalter_min": round(alter / 60), "veraltet": veraltet}

        # 1) Offene Positionen verwalten (auch wenn die Daten alt sind: Stop/Ziel aus den Kerzen prüfen)
        for kerze in kerzen[-4:]:
            for trade in self.konto.kerze_pruefen(symbol, kerze):
                self._trade_gemeldet(trade)
        if not veraltet:
            for trade in self.konto.preis_pruefen(symbol, preis, jetzt):
                self._trade_gemeldet(trade)

        # 2) Nur bei einer neu abgeschlossenen Kerze entscheiden
        abgeschlossen = kerzen[:-1]
        if self.letzte_kerze.get(symbol) == abgeschlossen[-1]["zeit"]:
            return
        self.letzte_kerze[symbol] = abgeschlossen[-1]["zeit"]
        if not risiko.in_handelszeit(jetzt, self.regeln):
            return  # außerhalb der Handelszeit: nichts entscheiden, nichts protokollieren
        if veraltet:
            self._protokoll(symbol, "WAIT", [f"Daten {round(alter / 60)} Minuten alt ({quelle}) – ich handle "
                                             "nicht mit veralteten Kursen"], preis=preis)
            return
        offen = next((p for p in self.konto.zustand["offene"] if p["symbol"] == symbol), None)
        if offen:
            stand = paper.PaperKonto._ergebnis(offen, preis)
            self._protokoll(symbol, "HOLD", [f"{offen['richtung']} seit {datetime.fromtimestamp(offen['eroeffnet']):%H:%M}, "
                                             f"aktuell {stand:+.2f} $, Stop {offen['stop']:.{stellen}f}, Ziel {offen['ziel']:.{stellen}f}"],
                            confidence=offen["confidence"], preis=preis)
            return

        kosten = self.regeln.kosten.get(symbol.upper(), 0.0)
        name_strategie = getattr(self.e, "TRADER_STRATEGIE", {}).get(symbol.upper(), "pullback")
        variante = getattr(self.e, "TRADER_VARIANTE", {}).get(symbol.upper(), "basis")
        if not strategien.im_zeitfenster(variante, jetzt):
            return  # diese Variante handelt nur zu bestimmten Uhrzeiten
        signal = strategien.bewerten(name_strategie, abgeschlossen[-300:], h1[:-1][-250:], symbol, stellen, kosten)
        signal = strategien.variante_anwenden(signal, variante)
        if signal["aktion"] == "WAIT":
            self._protokoll(symbol, "WAIT", signal["gruende"], preis=preis)
            return
        try:
            news = self.news()
        except Exception:
            news = []
        erlaubt, gruende = risiko.pruefen(signal, symbol, jetzt, self.konto.risiko_daten(self.preise, self.status),
                                          self.regeln, news)
        s = signal["setup"]
        if erlaubt and not ((s["stop"] < preis < s["ziel"]) if s["richtung"] == "LONG" else (s["ziel"] < preis < s["stop"])):
            erlaubt, gruende = False, ["Kurs ist schon über Stop oder Ziel hinaus"]
        if not erlaubt:
            self._protokoll(symbol, "WAIT", [f"{signal['aktion']}-Signal (Confidence {signal['confidence']}) abgelehnt: "
                                             + "; ".join(gruende)] + signal["gruende"],
                            confidence=signal["confidence"], teile=signal["teile"], preis=preis)
            return
        text = (f"{symbol} {s['richtung']} bei {preis:.{stellen}f}, Stop {s['stop']:.{stellen}f}, "
                f"Ziel {s['ziel']:.{stellen}f}, Confidence {signal['confidence']}")
        if self.stufe == 0:
            self._protokoll(symbol, signal["aktion"], ["NUR SIGNAL (Stufe 0)"] + signal["gruende"],
                            confidence=signal["confidence"], teile=signal["teile"], preis=preis)
            self.melden(f"Trading-Signal: {text}.")
            return
        schritt = self.regeln.einheiten_schritt.get(symbol.upper(), 0.01)
        einheiten = risiko.positionsgroesse(self.konto.equity(self.preise), self.regeln.risiko_prozent,
                                            preis, s["stop"], kosten, schritt)
        if einheiten <= 0:
            self._protokoll(symbol, "WAIT", ["Positionsgröße wäre 0 (Stop zu weit für das Risiko-Limit)"], preis=preis)
            return
        position = self.konto.eroeffnen(symbol, signal, einheiten, jetzt, preis=preis)
        self._protokoll(symbol, signal["aktion"], [f"PAPER-TRADE eröffnet: {einheiten} Einheiten, Risiko "
                                                   f"{position['risiko_betrag']:.0f} $"] + signal["gruende"],
                        confidence=signal["confidence"], teile=signal["teile"], preis=preis)
        self.melden(f"Paper-Trade eröffnet: {text}.")

    # ---------- Manuelle Paper-Trades (Wunsch des Boss, nur virtuelles Geld) ----------

    def manuell_eroeffnen(self, symbol, richtung, stop, ziel, risiko_prozent=None, begruendung=""):
        """Eröffnet einen MANUELLEN Paper-Trade zum aktuellen Kurs – mit denselben Risiko-Grenzen wie der Roboter
        (Tagesstopp, Drawdown, News-Sperre, max. Positionen, CRV mind. 1). Nie eine echte Order."""
        symbol = symbol.upper()
        richtung = richtung.upper().replace("KAUFEN", "LONG").replace("BUY", "LONG").replace("VERKAUFEN", "SHORT") \
            .replace("SELL", "SHORT")
        if richtung not in ("LONG", "SHORT"):
            return "Richtung bitte LONG (kaufen) oder SHORT (verkaufen)."
        try:
            name, stellen, quelle, kerzen = self.kerzen_holen(symbol, "M15", 50)
        except Exception as fehler:
            return f"Kein aktueller Kurs für {symbol}: {fehler}"
        preis = kerzen[-1]["close"]
        jetzt = time.time()
        stop, ziel = float(stop), float(ziel)
        if not ((stop < preis < ziel) if richtung == "LONG" else (ziel < preis < stop)):
            return (f"Stop/Ziel passen nicht zum Kurs {preis:.{stellen}f}: bei {richtung} muss der Stop "
                    f"{'darunter' if richtung == 'LONG' else 'darüber'} und das Ziel {'darüber' if richtung == 'LONG' else 'darunter'} liegen.")
        kosten = self.regeln.kosten.get(symbol, 0.0)
        r, chance = abs(preis - stop), abs(ziel - preis)
        signal = {"aktion": "BUY" if richtung == "LONG" else "SELL", "confidence": 0, "teile": {}, "manuell": True,
                  "strategie": "Manuell", "gruende": [f"MANUELL: {begruendung or 'ohne Begründung'}"],
                  "setup": {"richtung": richtung, "einstieg": preis, "stop": stop, "ziel": ziel, "kosten": kosten,
                            "crv": chance / r, "crv_netto": (chance - kosten) / (r + kosten), "min_crv": 1.0}}
        try:
            news = self.news()
        except Exception:
            news = []
        erlaubt, gruende = risiko.pruefen(signal, symbol, jetzt, self.konto.risiko_daten(self.preise, self.status),
                                          self.regeln, news)
        if not erlaubt:
            return "Abgelehnt von der Risiko-Engine: " + "; ".join(gruende)
        prozent = min(float(risiko_prozent or self.regeln.risiko_prozent), self.regeln.risiko_prozent)
        einheiten = risiko.positionsgroesse(self.konto.equity(self.preise), prozent, preis, stop, kosten,
                                            self.regeln.einheiten_schritt.get(symbol, 0.01))
        if einheiten <= 0:
            return "Positionsgröße wäre 0 – der Stop ist zu weit weg für das Risiko-Limit."
        p = self.konto.eroeffnen(symbol, signal, einheiten, jetzt, preis=preis)
        self.preise[symbol] = preis
        self._protokoll(symbol, signal["aktion"], [f"MANUELLER PAPER-TRADE #{p['id']}: {einheiten} Einheiten, "
                                                   f"Risiko {p['risiko_betrag']:.0f} $"] + signal["gruende"], preis=preis)
        warnung = ""
        bald = [n for n in news if 0 <= n["zeit"] - jetzt <= 60 * 60
                and n.get("waehrung") in risiko.NEWS_WAEHRUNGEN.get(symbol, {"USD"})]
        if bald:
            warnung = f" Achtung: in {round((bald[0]['zeit'] - jetzt) / 60)} Minuten kommen wichtige News ({bald[0].get('titel', '')})."
        return (f"Manueller Paper-Trade #{p['id']} eröffnet: {symbol} {richtung} bei {preis:.{stellen}f}, "
                f"Stop {stop:.{stellen}f}, Ziel {ziel:.{stellen}f}, {einheiten} Einheiten, Risiko {p['risiko_betrag']:.0f} $ "
                f"({prozent} %). Nur Spielgeld.{warnung}")

    def manuell_schliessen(self, position_id):
        p = next((x for x in self.konto.zustand["offene"] if x["id"] == int(position_id)), None)
        if p is None:
            return f"Keine offene Position mit Nummer {position_id}."
        try:
            kurs = self.kerzen_holen(p["symbol"], "M15", 5)[3][-1]["close"]
        except Exception:
            kurs = self.preise.get(p["symbol"], p["einstieg"])
        trade = self.konto.schliessen(p["id"], kurs, time.time(), "von Hand geschlossen")
        self._trade_gemeldet(trade)
        return f"Position #{p['id']} {p['symbol']} geschlossen bei {kurs}: {trade['ergebnis']:+.2f} $ ({trade['r']:+.2f} R)."

    def _trade_gemeldet(self, trade):
        self._protokoll(trade["symbol"], "SELL" if trade["richtung"] == "LONG" else "BUY",
                        [f"PAPER-TRADE geschlossen ({trade['grund']}): {trade['ergebnis']:+.2f} $, {trade['r']:+.2f} R"],
                        confidence=trade.get("confidence"), preis=trade["ausstieg"])
        self.melden(f"Paper-Trade {trade['symbol']} geschlossen, {trade['grund']}: {trade['ergebnis']:+.0f} Dollar.")

    def _drawdown_pruefen(self):
        daten = self.konto.risiko_daten(self.preise, self.status)
        drawdown = (daten["hoechststand"] - daten["equity"]) / daten["hoechststand"] * 100
        if drawdown >= self.regeln.max_drawdown_prozent and self.status != "gesperrt":
            for trade in self.konto.alle_schliessen(self.preise, time.time(), "Max. Drawdown"):
                self._trade_gemeldet(trade)
            self._status_setzen("gesperrt", f"Drawdown {drawdown:.1f} % erreicht")
            self.melden(f"Achtung: Der Trading-Roboter hat {drawdown:.1f} Prozent Drawdown erreicht und sich gesperrt. "
                        "Bitte die Ergebnisse prüfen, bevor er weitermacht.")

    # ---------- Dauerbetrieb ----------

    def starten(self):
        def schleife():
            while True:
                try:
                    self.schritt()
                    self.fehler_in_folge = 0
                except Exception as fehler:
                    self.fehler_in_folge += 1
                    print(f"[Trader-Fehler: {fehler}]")
                    if self.fehler_in_folge >= 3 and self.status == "aktiv":
                        self._status_setzen("pausiert", f"technischer Fehler: {fehler}"[:200])
                        self.melden("Der Trading-Roboter hat wegen technischer Fehler pausiert.")
                time.sleep(self.e.TRADER_PRUEF_SEKUNDEN)
        threading.Thread(target=schleife, daemon=True).start()

    def status_daten(self):
        with self._sperre:
            konto = self.konto.zustand
            heute = risiko.tagesbeginn(time.time())
            trades_heute = [t for t in konto["trades"] if risiko.tagesbeginn(t["geschlossen"]) == heute]
            equity = self.konto.equity(self.preise)
            offene = [dict(p, aktuell=self.preise.get(p["symbol"]),
                           stand=round(paper.PaperKonto._ergebnis(p, self.preise.get(p["symbol"], p["einstieg"])), 2))
                      for p in konto["offene"]]
            return {
                "status": self.status, "grund": self.status_grund, "stufe": self.stufe, "modus": "PAPER",
                "in_handelszeit": risiko.in_handelszeit(time.time(), self.regeln),
                "handelszeit": self.regeln.handelszeit, "maerkte": self.e.TRADER_MAERKTE,
                "markt_info": self.markt_info, "start": konto["start"], "balance": konto["balance"],
                "equity": equity, "heute": equity - konto["tagesstart_equity"],
                # Roboter-Statistik OHNE manuelle Trades (sonst wäre die Auswertung der Strategie verfälscht)
                "statistik": paper.statistik([t for t in konto["trades"] if not t.get("manuell")], konto["start"]),
                "statistik_manuell": paper.statistik([t for t in konto["trades"] if t.get("manuell")], konto["start"]),
                "statistik_heute": paper.statistik(trades_heute, konto["tagesstart_equity"]),
                "offene": offene, "trades": konto["trades"][-30:][::-1],
                "entscheidungen": list(self.entscheidungen)[:60], "letzter_durchgang": self.letzter_durchgang,
                "regeln": {"risiko": self.regeln.risiko_prozent, "tagesstopp": self.regeln.tagesstopp_prozent,
                           "max_drawdown": self.regeln.max_drawdown_prozent, "min_confidence": self.regeln.min_confidence},
            }
