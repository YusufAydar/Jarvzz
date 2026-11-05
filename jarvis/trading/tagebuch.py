"""
Trading-Tagebuch: jeder Trade mit Einstieg, Stop, Ergebnis und Notiz.
Die Auswertung zeigt, was funktioniert: Trefferquote, Ergebnis in R (Vielfache des Risikos),
beste/schlechteste Märkte. Gerade für eine FTMO-Challenge Gold wert.

"R" einfach erklärt: 1 R = der Betrag, den du riskiert hast (Abstand Einstieg–Stop).
+2 R heißt: doppelt so viel gewonnen wie riskiert. -1 R heißt: Stop-Loss getroffen.
"""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path


class Tagebuch:
    def __init__(self, datei):
        self.datei = Path(datei)
        self._sperre = threading.Lock()
        try:
            self.eintraege = json.loads(self.datei.read_text(encoding="utf-8"))
        except Exception:
            self.eintraege = []

    def _speichern(self):
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        self.datei.write_text(json.dumps(self.eintraege, ensure_ascii=False, indent=2), encoding="utf-8")

    def eintragen(self, symbol, richtung, einstieg=None, stop=None, ausstieg=None, gewinn=None,
                  notiz="", setup="", zeit=None):
        richtung = str(richtung).upper()
        if richtung not in ("LONG", "SHORT"):
            raise ValueError("Richtung muss LONG oder SHORT sein.")
        r = None
        if None not in (einstieg, stop, ausstieg) and einstieg != stop:
            risiko = abs(einstieg - stop)
            r = ((ausstieg - einstieg) if richtung == "LONG" else (einstieg - ausstieg)) / risiko
        with self._sperre:
            eintrag = {"id": max((e["id"] for e in self.eintraege), default=0) + 1,
                       "zeit": (zeit or datetime.now()).strftime("%Y-%m-%dT%H:%M"),
                       "symbol": symbol.upper(), "richtung": richtung, "einstieg": einstieg, "stop": stop,
                       "ausstieg": ausstieg, "r": None if r is None else round(r, 2), "gewinn": gewinn,
                       "setup": setup, "notiz": notiz}
            self.eintraege.append(eintrag)
            self._speichern()
        return eintrag

    def loeschen(self, eintrag_id):
        with self._sperre:
            vorher = len(self.eintraege)
            self.eintraege = [e for e in self.eintraege if e["id"] != int(eintrag_id)]
            self._speichern()
            return len(self.eintraege) < vorher

    def liste(self, tage=30, jetzt=None):
        grenze = ((jetzt or datetime.now()) - timedelta(days=tage)).strftime("%Y-%m-%dT%H:%M")
        return [e for e in self.eintraege if e["zeit"] >= grenze]

    def auswertung(self, tage=30, jetzt=None):
        trades = self.liste(tage, jetzt)
        mit_ergebnis = [e for e in trades if e["r"] is not None or e["gewinn"] is not None]

        def gewonnen(e):
            return (e["r"] if e["r"] is not None else e["gewinn"]) > 0

        r_werte = [e["r"] for e in trades if e["r"] is not None]
        geld = [e["gewinn"] for e in trades if e["gewinn"] is not None]
        pro_symbol = {}
        for e in mit_ergebnis:
            s = pro_symbol.setdefault(e["symbol"], {"trades": 0, "gewonnen": 0, "r": 0.0})
            s["trades"] += 1
            s["gewonnen"] += gewonnen(e)
            s["r"] += e["r"] or 0
        return {
            "tage": tage, "trades": len(trades), "mit_ergebnis": len(mit_ergebnis),
            "trefferquote": sum(map(gewonnen, mit_ergebnis)) / len(mit_ergebnis) if mit_ergebnis else None,
            "summe_r": sum(r_werte) if r_werte else None,
            "schnitt_r": sum(r_werte) / len(r_werte) if r_werte else None,
            "summe_gewinn": sum(geld) if geld else None,
            "bester": max(mit_ergebnis, key=lambda e: e["r"] if e["r"] is not None else e["gewinn"], default=None),
            "schlechtester": min(mit_ergebnis, key=lambda e: e["r"] if e["r"] is not None else e["gewinn"], default=None),
            "pro_symbol": pro_symbol,
        }


def auswertung_text(a):
    if not a["trades"]:
        return f"Keine Trades im Tagebuch in den letzten {a['tage']} Tagen."
    zeilen = [f"Tagebuch, letzte {a['tage']} Tage: {a['trades']} Trades"]
    if a["trefferquote"] is not None:
        zeilen.append(f"Trefferquote {a['trefferquote'] * 100:.0f} % ({a['mit_ergebnis']} mit Ergebnis)")
    if a["summe_r"] is not None:
        zeilen.append(f"Ergebnis {a['summe_r']:+.1f} R, im Schnitt {a['schnitt_r']:+.2f} R pro Trade")
    if a["summe_gewinn"] is not None:
        zeilen.append(f"Gewinn/Verlust gesamt {a['summe_gewinn']:+.2f}")
    if a["pro_symbol"]:
        zeilen.append("Pro Markt: " + "; ".join(
            f"{s} {v['gewonnen']}/{v['trades']} gewonnen, {v['r']:+.1f} R" for s, v in a["pro_symbol"].items()))
    return "\n".join(zeilen)
