"""
Paper-Konto: handelt mit VIRTUELLEM Geld zu echten Kursen. Hier wird nie eine echte Order geschickt.

- Eröffnen mit Stop-Loss und Take-Profit, Positionsgröße aus der Risiko-Engine
- Kosten (Spread + Kommission) werden bei jedem Trade abgezogen
- Stop-Loss und Take-Profit werden mit Hoch/Tief jeder Kerze geprüft. Werden in EINER Kerze
  beide berührt, zählt der Stop-Loss (vorsichtige Annahme)
- Stop-Management (optional je Trade): Stop auf Einstand ziehen, sobald der Trade X R im Plus war,
  und/oder Stop nachziehen (Trailing). Der neue Stop gilt erst ab der NÄCHSTEN Kerze (vorsichtig).
- Jeder Trade wird vollständig dokumentiert (Zeit, Kurse, Größe, Strategie, Begründung, Score, Ergebnis)
"""

import json
import threading
from pathlib import Path

from trader import risiko


class PaperKonto:
    def __init__(self, start, datei=None):
        self.datei = Path(datei) if datei else None
        self._sperre = threading.RLock()
        self.zustand = {"start": start, "balance": start, "hoechststand": start, "offene": [], "trades": [],
                        "tag": None, "tagesstart_equity": start, "verlustserie": 0, "naechste_id": 1}
        if self.datei and self.datei.exists():
            try:
                self.zustand.update(json.loads(self.datei.read_text(encoding="utf-8")))
            except Exception:
                pass

    # ---------- Speichern ----------

    def _speichern(self):
        if self.datei:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            self.datei.write_text(json.dumps(self.zustand, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- Zahlen ----------

    def equity(self, preise=None):
        """Kontostand inkl. nicht realisierter Gewinne/Verluste (preise: {symbol: aktueller Kurs})."""
        offen = 0.0
        for p in self.zustand["offene"]:
            kurs = (preise or {}).get(p["symbol"], p["einstieg"])
            offen += self._ergebnis(p, kurs)
        return self.zustand["balance"] + offen

    @staticmethod
    def _ergebnis(p, kurs):
        bewegung = (kurs - p["einstieg"]) if p["richtung"] == "LONG" else (p["einstieg"] - kurs)
        return bewegung * p["einheiten"] - p["kosten"] * p["einheiten"]

    def tag_pruefen(self, zeitstempel, preise=None):
        """Beim ersten Blick an einem neuen Handelstag: Tagesstart merken, Verlustserie zurücksetzen."""
        with self._sperre:
            tag = risiko.tagesbeginn(zeitstempel)
            if self.zustand["tag"] != tag:
                self.zustand["tag"] = tag
                self.zustand["tagesstart_equity"] = self.equity(preise)
                self.zustand["verlustserie"] = 0
                self._speichern()

    def risiko_daten(self, preise=None, status="aktiv"):
        eq = self.equity(preise)
        return {"equity": eq, "tagesstart_equity": self.zustand["tagesstart_equity"],
                "hoechststand": max(self.zustand["hoechststand"], eq), "verlustserie": self.zustand["verlustserie"],
                "offene": list(self.zustand["offene"]), "status": status}

    # ---------- Handeln ----------

    def eroeffnen(self, symbol, signal, einheiten, zeitstempel, preis=None):
        s = signal["setup"]
        with self._sperre:
            p = {"id": self.zustand["naechste_id"], "symbol": symbol, "richtung": s["richtung"],
                 "einstieg": preis if preis is not None else s["einstieg"], "stop": s["stop"], "ziel": s["ziel"],
                 "einheiten": einheiten, "kosten": s.get("kosten", 0.0), "eroeffnet": zeitstempel,
                 "confidence": signal["confidence"], "teile": signal.get("teile", {}),
                 "begruendung": signal.get("gruende", []), "strategie": signal.get("strategie", "Trend-Pullback"),
                 "stop_start": s["stop"], "management": s.get("management") or {},
                 "manuell": bool(signal.get("manuell")),
                 "risiko_betrag": (abs((preis or s["einstieg"]) - s["stop"]) + s.get("kosten", 0.0)) * einheiten}
            self.zustand["naechste_id"] += 1
            self.zustand["offene"].append(p)
            self._speichern()
            return p

    def schliessen(self, position_id, kurs, zeitstempel, grund):
        with self._sperre:
            p = next((x for x in self.zustand["offene"] if x["id"] == position_id), None)
            if p is None:
                return None
            self.zustand["offene"].remove(p)
            ergebnis = round(self._ergebnis(p, kurs), 2)  # gebucht wird auf den Cent genau
            trade = dict(p, ausstieg=kurs, geschlossen=zeitstempel, grund=grund, ergebnis=ergebnis,
                         gebuehren=round(p["kosten"] * p["einheiten"], 2),
                         r=round(ergebnis / p["risiko_betrag"], 2) if p["risiko_betrag"] else None)
            self.zustand["trades"].append(trade)
            self.zustand["balance"] += ergebnis
            self.zustand["hoechststand"] = max(self.zustand["hoechststand"], self.zustand["balance"])
            self.zustand["verlustserie"] = self.zustand["verlustserie"] + 1 if ergebnis < 0 else 0
            self._speichern()
            return trade

    def kerze_pruefen(self, symbol, kerze):
        """Prüft eine Kerze gegen Stop-Loss/Take-Profit aller offenen Positionen dieses Markts."""
        geschlossen = []
        for p in [x for x in self.zustand["offene"] if x["symbol"] == symbol]:
            if kerze["zeit"] < p["eroeffnet"]:  # nur Kerzen, die NACH dem Einstieg begonnen haben
                continue
            long = p["richtung"] == "LONG"
            stop_getroffen = kerze["low"] <= p["stop"] if long else kerze["high"] >= p["stop"]
            ziel_getroffen = kerze["high"] >= p["ziel"] if long else kerze["low"] <= p["ziel"]
            if stop_getroffen:  # bei beiden in einer Kerze: Stop zählt (vorsichtig)
                geschlossen.append(self.schliessen(p["id"], p["stop"], kerze["zeit"], self._stop_name(p)))
            elif ziel_getroffen:
                geschlossen.append(self.schliessen(p["id"], p["ziel"], kerze["zeit"], "Take-Profit"))
            else:
                self._stop_nachziehen(p, kerze["high"], kerze["low"])
        return [t for t in geschlossen if t]

    @staticmethod
    def _stop_name(p):
        if p["stop"] == p.get("stop_start", p["stop"]):
            return "Stop-Loss"
        gesichert = (p["stop"] >= p["einstieg"]) if p["richtung"] == "LONG" else (p["stop"] <= p["einstieg"])
        return "Nachgezogener Stop (im Plus/Einstand)" if gesichert else "Nachgezogener Stop"

    def _stop_nachziehen(self, p, hoch, tief):
        """Break-even und Trailing-Stop. Der Stop wird nur in Gewinnrichtung bewegt, nie zurück."""
        m = p.get("management") or {}
        r = abs(p["einstieg"] - p.get("stop_start", p["stop"]))
        if not m or not r:
            return
        long = p["richtung"] == "LONG"
        bester = hoch if long else tief
        im_plus_r = ((bester - p["einstieg"]) if long else (p["einstieg"] - bester)) / r
        kandidaten = []
        if m.get("breakeven_r") and im_plus_r >= m["breakeven_r"]:
            kandidaten.append(p["einstieg"] + p["kosten"] if long else p["einstieg"] - p["kosten"])
        if m.get("trail_r") and im_plus_r >= m.get("trail_start_r", 0):
            kandidaten.append(bester - m["trail_r"] * r if long else bester + m["trail_r"] * r)
        if not kandidaten:
            return
        neuer = max(kandidaten) if long else min(kandidaten)
        if (neuer > p["stop"]) if long else (neuer < p["stop"]):
            with self._sperre:
                p["stop"] = neuer
                self._speichern()

    def preis_pruefen(self, symbol, preis, zeitstempel):
        """Live: aktueller Kurs jenseits von Stop-Loss/Take-Profit? Dann zu diesem Kurs schließen."""
        geschlossen = []
        for p in [x for x in self.zustand["offene"] if x["symbol"] == symbol]:
            long = p["richtung"] == "LONG"
            if (preis <= p["stop"]) if long else (preis >= p["stop"]):
                geschlossen.append(self.schliessen(p["id"], preis, zeitstempel, self._stop_name(p)))
            elif (preis >= p["ziel"]) if long else (preis <= p["ziel"]):
                geschlossen.append(self.schliessen(p["id"], preis, zeitstempel, "Take-Profit"))
            else:
                self._stop_nachziehen(p, preis, preis)
        return [t for t in geschlossen if t]

    def alle_schliessen(self, preise, zeitstempel, grund):
        return [t for t in (self.schliessen(p["id"], preise.get(p["symbol"], p["einstieg"]), zeitstempel, grund)
                            for p in list(self.zustand["offene"])) if t]

    def zuruecksetzen(self, start):
        with self._sperre:
            self.zustand = {"start": start, "balance": start, "hoechststand": start, "offene": [], "trades": [],
                            "tag": None, "tagesstart_equity": start, "verlustserie": 0, "naechste_id": 1}
            self._speichern()


def statistik(trades, start):
    """Kennzahlen aus abgeschlossenen Trades: Win-Rate, Profit-Faktor, Drawdown, R."""
    if not trades:
        return {"trades": 0, "gewinner": 0, "verlierer": 0, "win_rate": None, "profit_faktor": None,
                "netto": 0.0, "max_drawdown_prozent": 0.0, "schnitt_r": None, "summe_r": None, "gebuehren": 0.0}
    gewinne = sum(t["ergebnis"] for t in trades if t["ergebnis"] > 0)
    verluste = -sum(t["ergebnis"] for t in trades if t["ergebnis"] < 0)
    stand = hoch = start
    max_dd = 0.0
    for t in sorted(trades, key=lambda t: t["geschlossen"]):
        stand += t["ergebnis"]
        hoch = max(hoch, stand)
        max_dd = max(max_dd, (hoch - stand) / hoch * 100)
    r_werte = [t["r"] for t in trades if t.get("r") is not None]
    return {"trades": len(trades), "gewinner": sum(1 for t in trades if t["ergebnis"] > 0),
            "verlierer": sum(1 for t in trades if t["ergebnis"] <= 0),
            "win_rate": sum(1 for t in trades if t["ergebnis"] > 0) / len(trades),
            "profit_faktor": gewinne / verluste if verluste else (float("inf") if gewinne else None),
            "netto": sum(t["ergebnis"] for t in trades), "max_drawdown_prozent": max_dd,
            "schnitt_r": sum(r_werte) / len(r_werte) if r_werte else None,
            "summe_r": sum(r_werte) if r_werte else None,
            "gebuehren": sum(t.get("gebuehren", 0) for t in trades)}
