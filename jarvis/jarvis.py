"""
JARVIS – Startpunkt.

Starten:
    python jarvis.py          -> Sprachmodus (Mikrofon + Stimme)
    python jarvis.py --text   -> Textmodus (tippen statt sprechen, gut zum Testen)

Im Sprachmodus: Sag "Jarvis" und dann deine Frage, z. B. "Jarvis, wie spät ist es?"
Beenden: "Jarvis, beenden" sagen oder Strg+C drücken.
"""

import argparse
import os
import sys
import threading
import time
from pathlib import Path

import einstellungen
import stimme
import termine
import vollzugriff
from gehirn import Gehirn
from werkzeuge import Werkzeugkasten

BEENDEN_WOERTER = ("beenden", "schlafen", "ausschalten", "auf wiedersehen", "tschüss")


def env_datei_laden():
    """Liest den API-Schlüssel aus der Datei jarvis/.env (Zeilen wie NAME=wert)."""
    datei = Path(einstellungen.JARVIS_ORDNER) / ".env"
    if not datei.exists():
        return
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if zeile and not zeile.startswith("#") and "=" in zeile:
            name, wert = zeile.split("=", 1)
            os.environ.setdefault(name.strip(), wert.strip().strip('"').strip("'"))


def erinnerungs_waechter(kalender, nur_text, stopp):
    """Läuft im Hintergrund und meldet fällige Erinnerungen und Termine."""
    while not stopp.is_set():
        for eintrag in kalender.faellige():
            stimme.sprechen(termine.meldung_fuer(eintrag), nur_text)
        stopp.wait(15)  # alle 15 Sekunden nachsehen


def ist_beenden(befehl):
    klein = befehl.lower().strip(" .!?")
    return any(klein == w or klein.startswith(w) for w in BEENDEN_WOERTER)


def textmodus(gehirn):
    print("Textmodus – tippe deine Frage (oder 'beenden'):")
    while True:
        try:
            befehl = input("Du: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not befehl:
            continue
        if ist_beenden(befehl):
            break
        stimme.sprechen(gehirn.frage(befehl), nur_text=True)


def sprach_bestaetigung(ohr):
    """Fragt per Stimme nach, ob eine riskante Aktion erlaubt ist. Details stehen im Fenster."""
    def bestaetigen(art, beschreibung, details):
        print("\n" + "=" * 60 + f"\nJARVIS MÖCHTE: {beschreibung}\n" + "-" * 60)
        print(details if len(details) < 3000 else details[:3000] + "\n…")
        print("=" * 60)
        stimme.sprechen(f"Ich möchte Folgendes tun: {beschreibung}. Soll ich? Bitte mit Ja oder Nein antworten.")
        antwort = ohr.hoeren(warten_sekunden=einstellungen.BESTAETIGUNG_SEKUNDEN, max_satz_sekunden=5)
        print(f"(gehört: {antwort})")
        ok = vollzugriff.ist_ja(stimme.wake_wort_entfernen(antwort or "")[1])
        stimme.sprechen("In Ordnung." if ok else "Abgebrochen.")
        return ok
    return bestaetigen


def sprachmodus(gehirn, ohr):
    print(f"Ich höre zu. Sag '{einstellungen.WAKE_WORT.capitalize()}' und dann deine Frage.")
    letzte_antwort = 0.0
    while True:
        text = ohr.hoeren()
        if not text:
            continue
        print(f"(gehört: {text})")

        gerufen, befehl = stimme.wake_wort_entfernen(text)
        im_gespraech = time.time() - letzte_antwort < einstellungen.NACHFRAGE_SEKUNDEN
        if not gerufen and not im_gespraech:
            continue  # nicht mit Jarvis gesprochen

        if gerufen and not befehl:
            stimme.sprechen("Ja?")
            befehl = ohr.hoeren(warten_sekunden=6)
            if not befehl:
                continue
            print(f"(gehört: {befehl})")

        if ist_beenden(befehl):
            break
        antwort = gehirn.frage(befehl)
        stimme.sprechen(antwort)
        letzte_antwort = time.time()


def main():
    parser = argparse.ArgumentParser(description="Jarvis – dein Sprachassistent")
    parser.add_argument("--text", action="store_true", help="Tippen statt sprechen")
    args = parser.parse_args()

    env_datei_laden()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Es fehlt der API-Schlüssel. Lege die Datei jarvis/.env an (siehe README).")
        sys.exit(1)

    kalender = termine.Terminkalender(einstellungen.TERMINE_DATEI)
    ohr = None if args.text else stimme.Ohr()
    bestaetigen = vollzugriff.bestaetigung_konsole if args.text else sprach_bestaetigung(ohr)
    gehirn = Gehirn(Werkzeugkasten(kalender, bestaetigen=bestaetigen))

    stopp = threading.Event()
    threading.Thread(target=erinnerungs_waechter, args=(kalender, args.text, stopp),
                     daemon=True).start()

    stimme.sprechen(termine.tagesueberblick(kalender), nur_text=args.text)
    try:
        if args.text:
            textmodus(gehirn)
        else:
            sprachmodus(gehirn, ohr)
    except KeyboardInterrupt:
        pass
    finally:
        stopp.set()
        stimme.sprechen("Bis später.", nur_text=args.text)


if __name__ == "__main__":
    main()
