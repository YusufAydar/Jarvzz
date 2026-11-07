"""
Großer Backtest mit Dukascopy-Historie (läuft in GitHub Actions, Workflow backtest.yml).

  python backtest_lauf.py laden 730    lädt die Kurse (gespeichert in jarvis/daten/historie, wird zwischengespeichert)
  python backtest_lauf.py rechnen 730  rechnet alles und schreibt backtest_ergebnis.md

Zwei Teile:
  A) LANGZEIT: bis zu 20 Jahre 1-Stunden-Kerzen auf vielen Märkten (Einstieg H1, Trend H4). Zeigt, ob eine
     Strategie in JEDER Marktphase funktioniert (Finanzkrise 2008, Corona 2020, Zinswende 2022 …).
     Gemessen wird der „rohe“ Vorteil OHNE Drawdown-Sperre (sonst würde der Test beim ersten schlechten Jahr enden).
  B) DAYTRADING: 2 Jahre 15-Minuten-Kerzen mit allen FTMO-Grenzen, so wie der Roboter live handelt.

Laden und Rechnen sind getrennt, damit schon geladene Daten auch dann gesichert werden, wenn der Download zu
lange dauert (der nächste Lauf macht weiter). Beim Rechnen dürfen bis zu 20 % der Tage fehlen.
"""

import copy
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jarvis"))

import einstellungen  # noqa: E402
from trader import backtest, risiko, strategien  # noqa: E402
from trading import historie  # noqa: E402

JAHRE = 20
# Teil A: viele Märkte (USDJPY fehlt bewusst: dort wäre der Gewinn in Yen, das Paper-Konto rechnet in Dollar)
LANGZEIT_MAERKTE = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "US30", "US500", "US100", "GER40"]
LANGZEIT_STRATEGIEN = ["pullback", "mean_reversion"]          # Breakouts brauchen M15 (Eröffnungsspanne)
LANGZEIT_VARIANTEN = ["basis", "breakeven", "trailing", "london", "newyork"]
# Teil B: Daytrading-Märkte (auch solche, die der Roboter gerade nicht handelt, z. B. US100)
MAERKTE = list(dict.fromkeys(einstellungen.TRADER_MAERKTE + ["XAUUSD", "US100", "EURUSD"]))
FEINTUNING = {"XAUUSD": "pullback", "EURUSD": "pullback"}

MODUS = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].isdigit() else "rechnen"
TAGE = int(next((a for a in sys.argv[1:] if a.isdigit()), 730))


def zeit_anzeige(markt, einheit):
    start = time.time()

    def fortschritt(erledigt, gesamt):
        if erledigt % 50 == 0 or erledigt == gesamt:
            print(f"  {markt}: {erledigt}/{gesamt} {einheit} ({time.time() - start:.0f} s)", flush=True)
    return fortschritt


def m15(markt, max_fehler_anteil, info=None, nur_gespeichert=False):
    return historie.m15_laden(markt, TAGE, fortschritt=zeit_anzeige(markt, "Tage"), max_fehler_anteil=max_fehler_anteil,
                              info=info, nur_gespeichert=nur_gespeichert)


def h1(markt, info=None):
    return historie.h1_laden(markt, JAHRE, fortschritt=zeit_anzeige(markt, "Monate"), info=info)


if MODUS == "laden":
    # Zuerst die Stundenkerzen (schnell: eine Datei pro Monat), dann die 15-Minuten-Kerzen (eine Datei pro Tag)
    for markt in LANGZEIT_MAERKTE:
        try:
            h1(markt)
            print(f"{markt}: {JAHRE} Jahre H1 geladen", flush=True)
        except Exception as fehler:
            print(f"{markt} H1: {fehler}", flush=True)
    for markt in MAERKTE:
        try:
            m15(markt, 1.0)
            print(f"{markt}: M15 geladen", flush=True)
        except Exception as fehler:
            print(f"{markt}: {fehler}", flush=True)
    sys.exit(0)

regeln = risiko.Regeln(einstellungen)
# Langzeit: roher Vorteil ohne Drawdown-Sperre und ohne Verlustserien-Pause (der Drawdown wird trotzdem gemessen)
regeln_roh = copy.copy(regeln)
regeln_roh.max_drawdown_prozent = 100.0
regeln_roh.verlustserie_pause = 10 ** 6

texte = [f"# Backtest Trading-Roboter (Dukascopy)\n",
         f"## A) Langzeit: bis zu {JAHRE} Jahre, Einstieg H1, Trend H4, ohne Drawdown-Sperre\n"]
rangliste = []
for markt in LANGZEIT_MAERKTE:
    try:
        info = {}
        kerzen = h1(markt, info)
        print(f"  {markt}: {len(kerzen)} H1-Kerzen ab {info.get('beginn')}, rechne ...", flush=True)
        ergebnisse = backtest.vergleich(markt, kerzen, regeln_roh, einstellungen.TRADER_KONTO_START,
                                        LANGZEIT_STRATEGIEN, zeitrahmen="H1")
        varianten = backtest.varianten_vergleich(markt, kerzen, regeln_roh, einstellungen.TRADER_KONTO_START,
                                                 "pullback", LANGZEIT_VARIANTEN, zeitrahmen="H1")
        for e in ergebnisse + varianten:
            rangliste.append((backtest.urteil(e, regeln_roh)[0] == "BESTANDEN", e["statistik"]["profit_faktor"] or 0,
                              markt, e))
        text = (f"Daten ab {info.get('beginn')}" + (f", {info['fehlend']} Monate fehlen" if info.get("fehlend") else "")
                + "\n" + backtest.vergleich_text(ergebnisse, regeln_roh) + "\n\n"
                + backtest.varianten_text(varianten, regeln_roh) + "\n\n"
                + "\n\n".join(backtest.text(e, regeln_roh) for e in ergebnisse))
    except Exception as fehler:
        text = f"{markt}: FEHLER {fehler}"
    print(text, flush=True)
    texte.append("```\n" + text + "\n```\n")

if rangliste:
    rangliste.sort(key=lambda x: (x[0], x[1]), reverse=True)
    zeilen = ["### Rangliste Langzeit (beste zuerst)", ""]
    for bestanden, pf, markt, e in rangliste[:10]:
        s = e["statistik"]
        plus = sum(1 for v in e["jahre"].values() if v["netto"] > 0)
        zeilen.append(f"- {'✅' if bestanden else '❌'} **{markt} {e['strategie']}**: {s['trades']} Trades, PF {pf:.2f}, "
                      f"Netto {s['netto']:+.0f} $, max. Drawdown {s['max_drawdown_prozent']:.1f} %, "
                      f"{plus}/{len(e['jahre'])} Jahre im Plus")
    texte.insert(2, "\n".join(zeilen) + "\n")

texte.append(f"## B) Daytrading: {TAGE} Tage M15, mit allen FTMO-Grenzen\n")
for markt in MAERKTE:
    try:
        info = {}
        kerzen = m15(markt, 0.2, info, nur_gespeichert=True)
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
texte.append("> Vergangene Ergebnisse garantieren nichts. GER40 wird in Euro gehandelt – im Test wie Dollar gerechnet.")
Path("backtest_ergebnis.md").write_text("\n".join(texte), encoding="utf-8")
