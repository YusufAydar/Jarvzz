"""
Erinnerungen und Termine.

Alles wird in einer einfachen Datei gespeichert (jarvis/daten/termine.json),
damit nichts verloren geht, wenn du Jarvis neu startest.
"""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

ZEITFORMAT = "%Y-%m-%dT%H:%M"


class Terminkalender:
    def __init__(self, datei):
        self.datei = Path(datei)
        self._sperre = threading.Lock()  # damit sich zwei Programmteile nicht in die Quere kommen
        self.eintraege = self._laden()

    # ---------- Speichern & Laden ----------

    def _laden(self):
        if self.datei.exists():
            try:
                return json.loads(self.datei.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
        return []

    def _speichern(self):
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        self.datei.write_text(json.dumps(self.eintraege, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    # ---------- Was Jarvis damit machen kann ----------

    def hinzufuegen(self, art, text, zeitpunkt, minuten_vorher=0):
        """
        art:        "erinnerung" oder "termin"
        zeitpunkt:  Text wie "2026-11-06T09:00"
        minuten_vorher: so viele Minuten VOR dem Zeitpunkt meldet sich Jarvis
        """
        zeit = datetime.strptime(zeitpunkt, ZEITFORMAT)
        melden_um = zeit - timedelta(minutes=int(minuten_vorher or 0))
        with self._sperre:
            neue_id = max((e["id"] for e in self.eintraege), default=0) + 1
            eintrag = {
                "id": neue_id,
                "art": art,
                "text": text,
                "zeit": zeit.strftime(ZEITFORMAT),
                "melden_um": melden_um.strftime(ZEITFORMAT),
                "gemeldet": False,
            }
            self.eintraege.append(eintrag)
            self._speichern()
        return eintrag

    def auflisten(self, von=None, bis=None, nur_offene=True):
        """Gibt Einträge zurück, sortiert nach Zeit. von/bis sind optional (Text wie oben)."""
        ergebnis = []
        for e in self.eintraege:
            if nur_offene and e["gemeldet"] and e["art"] == "erinnerung":
                continue
            if von and e["zeit"] < von:
                continue
            if bis and e["zeit"] > bis:
                continue
            ergebnis.append(e)
        return sorted(ergebnis, key=lambda e: e["zeit"])

    def loeschen(self, eintrag_id):
        with self._sperre:
            vorher = len(self.eintraege)
            self.eintraege = [e for e in self.eintraege if e["id"] != int(eintrag_id)]
            self._speichern()
            return len(self.eintraege) < vorher

    def faellige(self, jetzt=None):
        """
        Gibt alle Einträge zurück, die JETZT gemeldet werden müssen,
        und merkt sie sich als "gemeldet", damit sie nicht doppelt kommen.
        """
        jetzt = (jetzt or datetime.now()).strftime(ZEITFORMAT)
        faellig = []
        with self._sperre:
            for e in self.eintraege:
                if not e["gemeldet"] and e["melden_um"] <= jetzt:
                    e["gemeldet"] = True
                    faellig.append(e)
            if faellig:
                self._speichern()
        return faellig

    def heute(self, jetzt=None):
        jetzt = jetzt or datetime.now()
        anfang = jetzt.strftime("%Y-%m-%dT00:00")
        ende = jetzt.strftime("%Y-%m-%dT23:59")
        return self.auflisten(von=anfang, bis=ende, nur_offene=False)


def meldung_fuer(eintrag):
    """Der Satz, den Jarvis sagt, wenn eine Erinnerung fällig ist."""
    uhrzeit = eintrag["zeit"][11:16]
    if eintrag["art"] == "termin":
        if eintrag["melden_um"] != eintrag["zeit"]:
            return f"Erinnerung: Um {uhrzeit} Uhr hast du den Termin {eintrag['text']}."
        return f"Es ist {uhrzeit} Uhr. Dein Termin beginnt: {eintrag['text']}."
    return f"Erinnerung: {eintrag['text']}"


def tagesueberblick(kalender, jetzt=None):
    """Kurzer Begrüßungssatz mit den Terminen von heute."""
    jetzt = jetzt or datetime.now()
    stunde = jetzt.hour
    gruss = "Guten Morgen" if stunde < 11 else ("Guten Tag" if stunde < 18 else "Guten Abend")
    heute = [e for e in kalender.heute(jetzt) if e["zeit"] >= jetzt.strftime(ZEITFORMAT)]
    if not heute:
        return f"{gruss}. Jarvis ist bereit. Für heute stehen keine weiteren Termine an."
    teile = [f"um {e['zeit'][11:16]} Uhr {e['text']}" for e in heute[:5]]
    return f"{gruss}. Jarvis ist bereit. Heute noch: " + ", ".join(teile) + "."
