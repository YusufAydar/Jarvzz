"""
Großer Backtest mit Dukascopy-Historie (läuft in GitHub Actions, Workflow backtest.yml).
Schreibt das Ergebnis nach backtest_ergebnis.md und zeigt den Fortschritt an.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jarvis"))

import einstellungen  # noqa: E402
from trader import backtest, risiko  # noqa: E402
from trading import historie  # noqa: E402

TAGE = int(sys.argv[1]) if len(sys.argv) > 1 else 730
regeln = risiko.Regeln(einstellungen)
texte = [f"# Backtest Trading-Roboter ({TAGE} Tage, Dukascopy)\n"]
for markt in einstellungen.TRADER_MAERKTE:
    start = time.time()

    def fortschritt(erledigt, gesamt, markt=markt):
        if erledigt % 50 == 0 or erledigt == gesamt:
            print(f"  {markt}: {erledigt}/{gesamt} Tage geladen ({time.time() - start:.0f} s)", flush=True)

    try:
        kerzen = historie.m15_laden(markt, TAGE, fortschritt=fortschritt)
        ergebnis = backtest.backtest(markt, kerzen, regeln, einstellungen.TRADER_KONTO_START)
        text = backtest.text(ergebnis, regeln)
    except Exception as fehler:
        text = f"{markt}: FEHLER {fehler}"
    print(text, flush=True)
    texte.append("```\n" + text + "\n```\n")
Path("backtest_ergebnis.md").write_text("\n".join(texte), encoding="utf-8")
