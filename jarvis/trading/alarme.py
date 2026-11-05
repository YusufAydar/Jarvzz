"""
Trading-Alarme: Jarvis beobachtet im Hintergrund und meldet sich von selbst.

Arten:
  preis_ueber / preis_unter  – Kurs steigt über bzw. fällt unter einen Wert
  rsi_ueber / rsi_unter      – RSI(14) auf dem gewählten Zeitrahmen
  setup                      – der Setup-Scanner findet ein Long- oder Short-Setup

Jeder Alarm meldet sich einmal und ist danach erledigt (außer "setup": der meldet sich
höchstens einmal pro Stunde, solange er aktiv ist).
"""

import json
import threading
import time
from pathlib import Path

ARTEN = ("preis_ueber", "preis_unter", "rsi_ueber", "rsi_unter", "setup")


class Alarme:
    def __init__(self, datei, kerzen_holen):
        self.datei = Path(datei)
        self.kerzen_holen = kerzen_holen  # Funktion(symbol, zeitrahmen, anzahl) -> (name, stellen, quelle, kerzen)
        self._sperre = threading.Lock()
        try:
            self.liste = json.loads(self.datei.read_text(encoding="utf-8"))
        except Exception:
            self.liste = []

    def _speichern(self):
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        self.datei.write_text(json.dumps(self.liste, ensure_ascii=False, indent=2), encoding="utf-8")

    def hinzufuegen(self, symbol, art, wert=None, zeitrahmen="M15"):
        if art not in ARTEN:
            raise ValueError(f"Unbekannte Alarm-Art. Möglich: {', '.join(ARTEN)}")
        if art != "setup" and wert is None:
            raise ValueError("Für diese Alarm-Art brauche ich einen Wert.")
        with self._sperre:
            neue_id = max((a["id"] for a in self.liste), default=0) + 1
            alarm = {"id": neue_id, "symbol": symbol, "art": art, "wert": wert,
                     "zeitrahmen": zeitrahmen.upper(), "aktiv": True, "zuletzt": 0}
            self.liste.append(alarm)
            self._speichern()
        return alarm

    def aktive(self):
        return [a for a in self.liste if a["aktiv"]]

    def loeschen(self, alarm_id):
        with self._sperre:
            vorher = len(self.liste)
            self.liste = [a for a in self.liste if a["id"] != int(alarm_id)]
            self._speichern()
            return len(self.liste) < vorher

    def pruefen(self, jetzt=None):
        """Prüft alle aktiven Alarme einmal. Gibt eine Liste von Meldungstexten zurück."""
        from trading import indikatoren as ind
        from trading import setups
        jetzt = jetzt or time.time()
        meldungen = []
        for a in self.aktive():
            try:
                name, stellen, _, kerzen = self.kerzen_holen(a["symbol"], a["zeitrahmen"], 200)
            except Exception:
                continue  # Quelle gerade nicht erreichbar – beim nächsten Mal
            preis = kerzen[-1]["close"]
            text = None
            if a["art"] == "preis_ueber" and preis >= a["wert"]:
                text = f"{a['symbol']} ist über {a['wert']} gestiegen, aktuell {preis:.{stellen}f}."
            elif a["art"] == "preis_unter" and preis <= a["wert"]:
                text = f"{a['symbol']} ist unter {a['wert']} gefallen, aktuell {preis:.{stellen}f}."
            elif a["art"] in ("rsi_ueber", "rsi_unter"):
                r = ind.rsi([k["close"] for k in kerzen])[-1]
                if r is not None and ((a["art"] == "rsi_ueber" and r >= a["wert"]) or
                                      (a["art"] == "rsi_unter" and r <= a["wert"])):
                    text = f"{a['symbol']}: RSI auf {a['zeitrahmen']} ist bei {r:.0f}."
            elif a["art"] == "setup" and jetzt - a.get("zuletzt", 0) > 3600:
                try:
                    _, _, _, h1 = self.kerzen_holen(a["symbol"], "H1", 200)
                except Exception:
                    continue
                e = setups.finde_setup(kerzen, h1, a["symbol"], stellen)
                if e.get("setup"):
                    text = setups.setup_text(e, stellen)
            if text:
                with self._sperre:
                    if a["art"] == "setup":
                        a["zuletzt"] = jetzt
                    else:
                        a["aktiv"] = False
                    self._speichern()
                meldungen.append("Alarm: " + text)
        return meldungen

    def beschreibung(self, a):
        namen = {"preis_ueber": "Preis über", "preis_unter": "Preis unter", "rsi_ueber": "RSI über",
                 "rsi_unter": "RSI unter", "setup": "Setup-Suche"}
        wert = "" if a["wert"] is None else f" {a['wert']}"
        return f"ID {a['id']}: {a['symbol']} {namen[a['art']]}{wert} ({a['zeitrahmen']})"


def waechter_starten(alarme, melden, pause=30):
    """Startet die Hintergrund-Beobachtung (einmal pro Programm)."""
    if getattr(alarme, "_laeuft", False):
        return
    alarme._laeuft = True

    def schleife():
        while True:
            for text in alarme.pruefen():
                melden(text)
            time.sleep(pause)

    threading.Thread(target=schleife, daemon=True).start()
