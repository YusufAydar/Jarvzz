"""
Startpunkt des Programms. Führt alle Schritte nacheinander aus:

  1. Rangliste laden und die besten Trader auswählen
  2. Für jeden Trader die Trades und offenen Positionen laden und speichern
  3. Den Tagesbericht erstellen und in den Ordner "berichte" schreiben

Starten mit:
    python main.py                 (10 Trader, Standard)
    python main.py --anzahl 100    (100 Trader)
    python main.py --nur-bericht   (nichts herunterladen, nur Bericht neu erstellen)
"""

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import bericht
import config
import datenbank
import hyperliquid_api


def daten_laden(db, anzahl, zeitraum, min_kontowert):
    print("Schritt 1: Lade die Rangliste von Hyperliquid ...")
    rangliste = hyperliquid_api.lade_rangliste()
    print(f"  {len(rangliste)} Wallets in der Rangliste gefunden.")
    top = hyperliquid_api.waehle_top_trader(rangliste, anzahl, zeitraum, min_kontowert)
    datenbank.speichere_top_trader(db, top)
    print(f"  Die besten {len(top)} Trader (sortiert nach Gewinn: {zeitraum}) sind ausgewählt.")

    print("Schritt 2: Lade Trades und Positionen für jeden Trader ...")
    fehler = 0
    for t in top:
        wallet = t["wallet"]
        try:
            ab = datenbank.letzter_fill_zeitpunkt(db, wallet)
            fills = hyperliquid_api.lade_fills(wallet, ab)
            neu = datenbank.speichere_fills(db, wallet, fills)
            positionen, kontowert = hyperliquid_api.lade_positionen(wallet)
            datenbank.speichere_positionen(db, wallet, positionen)
            if kontowert:
                datenbank.aktualisiere_kontowert(db, wallet, kontowert)
            print(f"  #{t['rang']:>3} {wallet}: {neu} neue Trades, "
                  f"{len(positionen)} offene Positionen")
        except Exception as e:  # Ein Fehler bei einer Wallet soll nicht alles stoppen
            fehler += 1
            print(f"  #{t['rang']:>3} {wallet}: FEHLER – {e}")
    if fehler == len(top):
        raise SystemExit("Für keine einzige Wallet konnten Daten geladen werden. Abbruch.")


def bericht_schreiben(db, ordner):
    print("Schritt 3: Erstelle den Tagesbericht ...")
    jetzt_ms = int(time.time() * 1000)
    text = bericht.erstelle_bericht(db, jetzt_ms, config.EINIGKEIT_MIN_TRADER,
                                    config.EINIGKEIT_MIN_ANTEIL)
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    datei = ordner / f"{tag}.md"
    datei.write_text(text, encoding="utf-8")
    (ordner / "aktuell.md").write_text(text, encoding="utf-8")  # immer der neueste Bericht
    print(f"  Bericht gespeichert: {datei}")


def main():
    parser = argparse.ArgumentParser(description="Analysiert die Top-Trader auf Hyperliquid.")
    parser.add_argument("--anzahl", type=int, default=config.STANDARD_ANZAHL_TRADER,
                        help="Wie viele Trader analysiert werden (Standard: 10)")
    parser.add_argument("--zeitraum", default=config.STANDARD_ZEITRAUM,
                        choices=["day", "week", "month", "allTime"],
                        help="Nach welchem Gewinn-Zeitraum sortiert wird")
    parser.add_argument("--min-kontowert", type=float, default=config.MIN_KONTOWERT,
                        help="Wallets mit weniger Kontowert (in $) werden übersprungen")
    parser.add_argument("--db", default=str(config.DATENBANK_DATEI), help="Pfad zur Datenbank")
    parser.add_argument("--berichte", default=str(config.BERICHTE_ORDNER), help="Ordner für Berichte")
    parser.add_argument("--nur-bericht", action="store_true",
                        help="Nichts herunterladen, nur den Bericht aus der Datenbank erstellen")
    args = parser.parse_args()

    db = datenbank.verbinden(args.db)
    if not args.nur_bericht:
        daten_laden(db, args.anzahl, args.zeitraum, args.min_kontowert)
    bericht_schreiben(db, args.berichte)
    print("Fertig!")


if __name__ == "__main__":
    main()
