"""Tests für die zusätzlichen Strategien (Breakouts, Mean-Reversion) und den Strategie-Vergleich."""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import einstellungen  # noqa: E402
from trader import backtest, risiko, strategien  # noqa: E402
from trading import indikatoren as ind  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    WIEN = ZoneInfo("Europe/Vienna")
except Exception:
    WIEN = None


def regeln(**x):
    werte = {k: getattr(einstellungen, k) for k in dir(einstellungen) if k.startswith("TRADER_")}
    werte.update(x)
    return risiko.Regeln(SimpleNamespace(**werte))


def tag_mit_ausbruch(nach_oben=True):
    """M15-Kerzen eines Dienstags: ruhige Nacht, Spanne 09:00–10:00 zwischen 99,5 und 100,5, dann Ausbruch."""
    start = int(datetime(2026, 11, 3, 0, 0, tzinfo=WIEN).timestamp())
    kerzen = []
    for i in range(44):  # 00:00 bis 10:45
        zeit = start + i * 900
        stunde = i / 4
        c = 100.0 + (0.3 if i % 2 else -0.3)
        o = c
        if stunde >= 10.5:  # 10:30: kräftiger Ausbruch
            o, c = (100.4, 101.6) if nach_oben else (99.6, 98.4)
        elif stunde >= 10:
            o = c = 100.2 if nach_oben else 99.8
        kerzen.append({"zeit": zeit, "open": o, "high": max(o, c) + 0.2, "low": min(o, c) - 0.2, "close": c})
    return kerzen[:43]  # letzte abgeschlossene Kerze = 10:30–10:45


class TestBollinger(unittest.TestCase):
    def test_baender(self):
        mitte, oben, unten = ind.bollinger([1.0] * 19 + [1.0, 3.0], 20, 2.0)
        self.assertIsNone(mitte[18])
        self.assertAlmostEqual(mitte[19], 1.0)
        self.assertAlmostEqual(oben[19], 1.0)            # keine Schwankung -> Bänder = Mitte
        self.assertGreater(oben[20], mitte[20] > unten[20] and mitte[20])


class TestOpeningRangeBreakout(unittest.TestCase):
    def test_ausbruch_nach_oben(self):
        s = strategien.bewerten("orb_london", tag_mit_ausbruch(True), None, "XAUUSD", 2, 0.0)
        self.assertEqual(s["aktion"], "BUY", s["gruende"])
        self.assertEqual(s["strategie"], "London-Breakout")
        self.assertLess(s["setup"]["stop"], s["setup"]["einstieg"])
        self.assertAlmostEqual(s["setup"]["crv"], 2.0)

    def test_ausbruch_nach_unten(self):
        s = strategien.bewerten("orb_london", tag_mit_ausbruch(False), None, "XAUUSD", 2, 0.0)
        self.assertEqual(s["aktion"], "SELL", s["gruende"])
        self.assertGreater(s["setup"]["stop"], s["setup"]["einstieg"])

    def test_nur_erster_ausbruch(self):
        kerzen = tag_mit_ausbruch(True)
        weiter = dict(kerzen[-1], zeit=kerzen[-1]["zeit"] + 900, open=101.6, close=102.0, high=102.2, low=101.4)
        s = strategien.bewerten("orb_london", kerzen + [weiter], None, "XAUUSD", 2, 0.0)
        self.assertEqual(s["aktion"], "WAIT")

    def test_ausserhalb_fenster(self):
        s = strategien.bewerten("orb_newyork", tag_mit_ausbruch(True), None, "XAUUSD", 2, 0.0)
        self.assertEqual(s["aktion"], "WAIT")
        self.assertIn("Einstiegsfenster", s["gruende"][0])

    def test_unbekannte_strategie(self):
        with self.assertRaises(ValueError):
            strategien.bewerten("zauberei", tag_mit_ausbruch(True), None, "XAUUSD")


class TestMeanReversion(unittest.TestCase):
    def test_nur_seitwaerts(self):
        h1 = [{"zeit": i * 3600, "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i} for i in range(80)]
        m15 = [{"zeit": i * 900, "open": 100, "high": 100.5, "low": 99.5, "close": 100} for i in range(80)]
        s = strategien.bewerten("mean_reversion", m15, h1, "EURUSD", 5, 0.0)
        self.assertEqual(s["aktion"], "WAIT")
        self.assertIn("Seitwärts", s["gruende"][0])

    def test_eigene_crv_grenze_nie_unter_1(self):
        sig = {"aktion": "BUY", "confidence": 80, "teile": {}, "gruende": [],
               "setup": {"richtung": "LONG", "einstieg": 100, "stop": 99, "ziel": 100.9, "crv": 0.9,
                         "crv_netto": 0.9, "kosten": 0, "min_crv": 0.5}}
        dienstag = datetime(2026, 11, 3, 11, 0, tzinfo=WIEN).timestamp()
        konto = {"equity": 10000, "tagesstart_equity": 10000, "hoechststand": 10000, "verlustserie": 0,
                 "offene": [], "status": "aktiv"}
        erlaubt, gruende = risiko.pruefen(sig, "EURUSD", dienstag, konto, regeln())
        self.assertFalse(erlaubt)
        self.assertTrue(any("unter 1.0" in g for g in gruende))
        sig["setup"].update(crv_netto=1.2, ziel=101.2, min_crv=1.0)
        erlaubt, gruende = risiko.pruefen(sig, "EURUSD", dienstag, konto, regeln())
        self.assertTrue(erlaubt, gruende)


class TestVergleich(unittest.TestCase):
    def test_alle_strategien_auf_denselben_daten(self):
        # 15 Handelstage mit Spanne + Ausbruch jeden Tag
        kerzen = []
        for tag in range(15):
            for k in tag_mit_ausbruch(tag % 2 == 0):
                kerzen.append(dict(k, zeit=k["zeit"] + tag * 86400))
        kerzen = [k for k in kerzen if datetime.fromtimestamp(k["zeit"], WIEN).weekday() < 5]
        ergebnisse = backtest.vergleich("XAUUSD", kerzen, regeln(TRADER_KOSTEN={}), 10000, fenster=50)
        self.assertEqual({e["strategie"] for e in ergebnisse}, set(strategien.NAMEN.values()))
        text = backtest.vergleich_text(ergebnisse, regeln())
        self.assertIn("STRATEGIE-VERGLEICH XAUUSD", text)
        london = next(e for e in ergebnisse if e["strategie"] == "London-Breakout")
        self.assertGreater(london["signale"], 0)


if __name__ == "__main__":
    unittest.main()
