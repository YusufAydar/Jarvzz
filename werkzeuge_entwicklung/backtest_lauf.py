"""
Großer Backtest mit Dukascopy-Historie (läuft in GitHub Actions, Workflow backtest.yml).

  python backtest_lauf.py laden 730    lädt die Kurse (gespeichert in jarvis/daten/historie, wird zwischengespeichert)
  python backtest_lauf.py rechnen 730  vergleicht alle Strategien je Markt und schreibt backtest_ergebnis.md

Getrennt, damit schon geladene Tage auch dann gesichert werden, wenn der Download zu lange dauert.
Beim Rechnen dürfen bis zu 20 % der Tage fehlen – das steht dann im Ergebnis.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jarvis"))

import einstellungen  # noqa: E402
from trader import backtest, risiko, strategien  # noqa: E402
from trading import historie  # noqa: E402

# Auch Märkte testen, die der Roboter gerade nicht handelt (z. B. US100), damit man Verbesserungen sieht
MAERKTE = list(dict.fromkeys(einstellungen.TRADER_MAERKTE + ["XAUUSD", "US100", "EURUSD"]))
# Feintuning (Varianten) nur für Märkte, auf denen eine Strategie in die Nähe von „bestanden“ kam
FEINTUNING = {"XAUUSD": "pullback", "EURUSD": "pullback"}

MODUS = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].isdigit() else "rechnen"
TAGE = int(next((a for a in sys.argv[1:] if a.isdigit()), 730))


def laden(markt, max_fehler_anteil, info=None, nur_gespeichert=False):
    start = time.time()

    def fortschritt(erledigt, gesamt):
        if erledigt % 50 == 0 or erledigt == gesamt:
            print(f"  {markt}: {erledigt}/{gesamt} Tage ({time.time() - start:.0f} s)", flush=True)

    return historie.m15_laden(markt, TAGE, fortschritt=fortschritt, max_fehler_anteil=max_fehler_anteil, info=info,
                               nur_gespeichert=nur_gespeichert)


if MODUS == "laden":
    for markt in MAERKTE:
        try:
            laden(markt, 1.0)
            print(f"{markt}: geladen", flush=True)
        except Exception as fehler:
            print(f"{markt}: {fehler}", flush=True)
    sys.exit(0)

regeln = risiko.Regeln(einstellungen)
texte = [f"# Strategie-Vergleich Trading-Roboter ({TAGE} Tage, Dukascopy)\n"]
for markt in MAERKTE:
    try:
        info = {}
        kerzen = laden(markt, 0.2, info, nur_gespeichert=True)
        print(f"  {markt}: {len(kerzen)} Kerzen ({info.get('fehlend', 0)} Tage fehlen), "
              f"teste {len(strategien.STRATEGIEN)} Strategien ...", flush=True)
        ergebnisse = backtest.vergleich(markt, kerzen, regeln, einstellungen.TRADER_KONTO_START)
        text = (f"Datenlücken: {info.get('fehlend', 0)} Tage fehlen\n" if info.get("fehlend") else "") + \
            backtest.vergleich_text(ergebnisse, regeln) + "\n\n" + "\n\n".join(backtest.text(e, regeln) for e in ergebnisse)
        if markt in FEINTUNING:
            print(f"  {markt}: Feintuning mit {len(strategien.VARIANTEN)} Varianten ...", flush=True)
            varianten = backtest.varianten_vergleich(markt, kerzen, regeln, einstellungen.TRADER_KONTO_START,
                                                     FEINTUNING[markt])
            text = backtest.varianten_text(varianten, regeln) + "\n\n" + text
    except Exception as fehler:
        text = f"{markt}: FEHLER {fehler}"
    print(text, flush=True)
    texte.append("```\n" + text + "\n```\n")
Path("backtest_ergebnis.md").write_text("\n".join(texte), encoding="utf-8")
