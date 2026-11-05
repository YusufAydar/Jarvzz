"""Tests für den Trading-Roboter: Strategie, Risiko-Engine, Paper-Konto, Backtest und Engine.
Alles mit selbstgebauten Kursreihen – ohne Internet, ohne echte Orders."""

import json
import math
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import einstellungen  # noqa: E402
from trader import backtest, paper, risiko, strategie  # noqa: E402
from trader.engine import TradingEngine  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    WIEN = ZoneInfo("Europe/Vienna")
except Exception:
    WIEN = None

DIENSTAG_10_UHR = datetime(2026, 11, 3, 10, 0, tzinfo=WIEN).timestamp()   # Handelszeit
SAMSTAG_10_UHR = datetime(2026, 11, 7, 10, 0, tzinfo=WIEN).timestamp()
DIENSTAG_22_UHR = datetime(2026, 11, 3, 22, 0, tzinfo=WIEN).timestamp()


def kerzen_aus(schluss, ende, schritt=900, spanne=0.3):
    """Kerzen, deren LETZTE bei `ende` beginnt (also gerade läuft)."""
    start = ende - (len(schluss) - 1) * schritt
    return [{"zeit": int(start + i * schritt), "open": c, "high": c + spanne, "low": c - spanne, "close": c}
            for i, c in enumerate(schluss)]


def long_reihe():
    reihe = [100 + i * 0.3 for i in range(150)]
    reihe += [reihe[-1] - j * 0.3 for j in range(1, 9)]
    tief = reihe[-1]
    return reihe + [tief + 0.3, tief + 0.6]


def regeln(**ueberschreiben):
    werte = {k: getattr(einstellungen, k) for k in dir(einstellungen) if k.startswith("TRADER_")}
    werte.update(ueberschreiben)
    return risiko.Regeln(SimpleNamespace(**werte))


def konto_daten(**x):
    d = {"equity": 10000, "tagesstart_equity": 10000, "hoechststand": 10000, "verlustserie": 0,
         "offene": [], "status": "aktiv"}
    d.update(x)
    return d


def signal(aktion="BUY", confidence=75, crv=2.0):
    return {"aktion": aktion, "confidence": confidence, "teile": {}, "gruende": ["Test"],
            "setup": {"richtung": "LONG" if aktion == "BUY" else "SHORT", "einstieg": 100.0,
                      "stop": 99.0 if aktion == "BUY" else 101.0, "ziel": 102.0 if aktion == "BUY" else 98.0,
                      "crv_netto": crv, "kosten": 0.0}}


class TestStrategie(unittest.TestCase):
    def test_kaufsignal_mit_nachvollziehbarem_score(self):
        k = kerzen_aus(long_reihe(), DIENSTAG_10_UHR)
        h1 = kerzen_aus([100 + i * 0.8 for i in range(250)], DIENSTAG_10_UHR, 3600, 0.5)
        s = strategie.bewerten(k, h1, "TEST", 2, kosten=0.05)
        self.assertEqual(s["aktion"], "BUY")
        self.assertEqual(set(s["teile"]), {"H1-Trendstärke", "Pullback-Qualität", "Momentum-Wende",
                                           "Chance/Risiko", "Volatilität normal", "H4-Rückenwind"})
        self.assertEqual(s["confidence"], sum(s["teile"].values()))
        self.assertTrue(0 <= s["confidence"] <= 100)
        self.assertLess(s["setup"]["crv_netto"], 2.0)   # Kosten machen das CRV schlechter
        self.assertGreaterEqual(len(s["gruende"]), 5)    # jede Entscheidung ist begründet

    def test_seitwaerts_heisst_warten(self):
        k = kerzen_aus([100 + (1 if i % 2 else -1) for i in range(200)], DIENSTAG_10_UHR)
        h1 = kerzen_aus([100 + (1 if i % 2 else -1) for i in range(120)], DIENSTAG_10_UHR, 3600)
        s = strategie.bewerten(k, h1, "TEST")
        self.assertEqual(s["aktion"], "WAIT")
        self.assertIn("kein klarer Trend", s["gruende"][0])

    def test_h4_nur_aus_vollstaendigen_bloecken(self):
        h1 = kerzen_aus([float(i) for i in range(10)], 4 * 3600 * 100 + 9 * 3600, 3600)
        h4 = strategie.h4_aus_h1(h1)
        self.assertTrue(all(b["zeit"] % (4 * 3600) == 0 for b in h4))
        self.assertEqual(len(h4), 2)  # 10 Stunden = 2 volle 4-Stunden-Blöcke


class TestRisiko(unittest.TestCase):
    def test_gutes_signal_ist_erlaubt(self):
        self.assertEqual(risiko.pruefen(signal(), "XAUUSD", DIENSTAG_10_UHR, konto_daten(), regeln()), (True, []))

    def test_jede_grenze_greift(self):
        r = regeln()
        faelle = [
            (signal(), SAMSTAG_10_UHR, konto_daten(), "außerhalb der Handelszeit"),
            (signal(), DIENSTAG_22_UHR, konto_daten(), "außerhalb der Handelszeit"),
            (signal(), DIENSTAG_10_UHR, konto_daten(equity=9790), "Tagesstopp"),
            (signal(), DIENSTAG_10_UHR, konto_daten(equity=9390, tagesstart_equity=9400, hoechststand=10000), "Drawdown"),
            (signal(), DIENSTAG_10_UHR, konto_daten(verlustserie=3), "Verluste in Folge"),
            (signal(), DIENSTAG_10_UHR, konto_daten(status="pausiert"), "pausiert"),
            (signal(confidence=55), DIENSTAG_10_UHR, konto_daten(), "Confidence"),
            (signal(crv=1.2), DIENSTAG_10_UHR, konto_daten(), "CRV"),
            (signal(), DIENSTAG_10_UHR, konto_daten(offene=[{"symbol": "XAUUSD", "richtung": "SHORT"}]), "schon eine Position"),
            (signal(), DIENSTAG_10_UHR, konto_daten(offene=[{"symbol": "A", "richtung": "LONG"},
                                                            {"symbol": "B", "richtung": "LONG"}]), "Maximum"),
        ]
        for sig, zeit, konto, erwartet in faelle:
            erlaubt, gruende = risiko.pruefen(sig, "XAUUSD", zeit, konto, r)
            self.assertFalse(erlaubt, erwartet)
            self.assertTrue(any(erwartet in g for g in gruende), (erwartet, gruende))

    def test_korrelation_und_news(self):
        r = regeln()
        erlaubt, g = risiko.pruefen(signal(), "US100", DIENSTAG_10_UHR,
                                    konto_daten(offene=[{"symbol": "US30", "richtung": "LONG"}]), r)
        self.assertFalse(erlaubt)
        self.assertTrue(any("Korrelation" in x for x in g))
        news = [{"zeit": DIENSTAG_10_UHR + 600, "waehrung": "USD", "titel": "NFP"}]
        erlaubt, g = risiko.pruefen(signal(), "XAUUSD", DIENSTAG_10_UHR, konto_daten(), r, news)
        self.assertFalse(erlaubt)
        self.assertTrue(any("NFP" in x for x in g))
        andere = [{"zeit": DIENSTAG_10_UHR + 600, "waehrung": "JPY", "titel": "BoJ"}]
        self.assertTrue(risiko.pruefen(signal(), "XAUUSD", DIENSTAG_10_UHR, konto_daten(), r, andere)[0])

    def test_positionsgroesse_ohne_martingale(self):
        # 1 % von 10.000 = 100 $, Stop 2 $ + Kosten 0,35 $ entfernt -> 42 Unzen (abgerundet)
        self.assertEqual(risiko.positionsgroesse(10000, 1.0, 2400, 2398, 0.35, 1), 42)
        # nach Verlusten kleineres Konto -> kleinere Position, nie größer
        self.assertLess(risiko.positionsgroesse(9000, 1.0, 2400, 2398, 0.35, 1), 42)


class TestPaperKonto(unittest.TestCase):
    def test_stop_hat_vorrang_und_kosten_zaehlen(self):
        k = paper.PaperKonto(10000)
        k.eroeffnen("XAUUSD", signal(), 50, 1000, preis=100.0)
        k.zustand["offene"][0]["kosten"] = 0.1
        # Kerze berührt Stop (99) UND Ziel (102) -> Stop zählt
        t = k.kerze_pruefen("XAUUSD", {"zeit": 1000, "open": 100, "high": 102.5, "low": 98.5, "close": 101})
        self.assertEqual(t[0]["grund"], "Stop-Loss")
        self.assertAlmostEqual(t[0]["ergebnis"], -50 * 1.0 - 50 * 0.1)
        self.assertEqual(k.zustand["verlustserie"], 1)

    def test_take_profit_und_r(self):
        k = paper.PaperKonto(10000)
        k.eroeffnen("XAUUSD", signal(), 50, 1000, preis=100.0)
        self.assertEqual(k.kerze_pruefen("XAUUSD", {"zeit": 0, "open": 100, "high": 103, "low": 100, "close": 102}), [])
        t = k.kerze_pruefen("XAUUSD", {"zeit": 1900, "open": 100, "high": 102.2, "low": 99.5, "close": 102})
        self.assertEqual(t[0]["grund"], "Take-Profit")
        self.assertAlmostEqual(t[0]["r"], 2.0)
        self.assertAlmostEqual(k.zustand["balance"], 10100)

    def test_speichern_tageswechsel_und_statistik(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "k.json"
            k = paper.PaperKonto(10000, datei)
            k.tag_pruefen(DIENSTAG_10_UHR)
            k.eroeffnen("EURUSD", signal(), 1000, DIENSTAG_10_UHR, preis=100.0)
            k.preis_pruefen("EURUSD", 98.9, DIENSTAG_10_UHR + 60)
            neu = paper.PaperKonto(10000, datei)
            self.assertEqual(len(neu.zustand["trades"]), 1)
            self.assertEqual(neu.zustand["verlustserie"], 1)
            neu.tag_pruefen(DIENSTAG_10_UHR + 86400)
            self.assertEqual(neu.zustand["verlustserie"], 0)
        s = paper.statistik([{"ergebnis": 200, "r": 2, "geschlossen": 1, "gebuehren": 1},
                             {"ergebnis": -100, "r": -1, "geschlossen": 2, "gebuehren": 1}], 10000)
        self.assertEqual((s["trades"], s["win_rate"], s["profit_faktor"]), (2, 0.5, 2.0))
        self.assertAlmostEqual(s["max_drawdown_prozent"], 100 / 10200 * 100)


class TestBacktest(unittest.TestCase):
    def daten(self):
        # Zwei Wochen Aufwärtstrend mit regelmäßigen Rücksetzern (Montag 00:00 Wien als Start)
        start = datetime(2026, 9, 7, 0, 0, tzinfo=WIEN).timestamp()
        preise, p = [], 2000.0
        for i in range(14 * 96):
            p += 0.9 * math.sin(i / 6) + 0.25
            preise.append(p)
        return [{"zeit": int(start + i * 900), "open": preise[i - 1] if i else preise[0],
                 "high": max(preise[i], preise[i - 1] if i else preise[0]) + 0.4,
                 "low": min(preise[i], preise[i - 1] if i else preise[0]) - 0.4, "close": preise[i]}
                for i in range(len(preise))]

    def test_backtest_ehrlich_und_vollstaendig(self):
        r = regeln(TRADER_MIN_CONFIDENCE=0)
        e = backtest.backtest("XAUUSD", self.daten(), r, 10000)
        self.assertTrue(e["trades"], "der synthetische Trend sollte Trades erzeugen")
        for t in e["trades"]:
            zeit = risiko.wien_zeit(t["eroeffnet"])
            self.assertLess(zeit.weekday(), 5)
            self.assertTrue("09:00" <= zeit.strftime("%H:%M") <= "21:00")
            self.assertGreater(t["einheiten"], 0)
            self.assertTrue(t["gebuehren"] > 0)
        s = e["statistik"]
        self.assertEqual(s["trades"], len(e["trades"]))
        self.assertAlmostEqual(e["ende_balance"], 10000 + s["netto"], places=4)
        status, _ = backtest.urteil(e, r)
        self.assertEqual(status, "ZU WENIG DATEN")   # zwei Wochen sind nie genug
        text = backtest.text(e, r)
        self.assertIn("Urteil", text)
        self.assertIn("Win-Rate", text)

    def test_zu_wenig_kerzen(self):
        with self.assertRaises(ValueError):
            backtest.backtest("XAUUSD", self.daten()[:100], regeln())

    def test_monte_carlo_und_kalibrierung(self):
        trades = [{"ergebnis": e, "r": e / 100, "confidence": c, "geschlossen": i}
                  for i, (e, c) in enumerate([(200, 85), (-100, 62), (-100, 65), (200, 75), (-100, 61), (200, 82)])]
        mc = backtest.monte_carlo(trades, 10000)
        self.assertLessEqual(mc["median_drawdown"], mc["drawdown_95"])
        k = backtest.kalibrierung(trades)
        self.assertEqual(k["80–100"]["gewinner"], 2)
        self.assertEqual(k["60–69"]["gewinner"], 0)


class TestEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.meldungen = []
        self.e = SimpleNamespace(**{k: getattr(einstellungen, k) for k in dir(einstellungen) if k.isupper()})
        self.e.TRADER_MAERKTE = ["XAUUSD"]
        self.e.TRADER_KOSTEN = {"XAUUSD": 0.01}   # Testpreise ~140 statt ~4000 -> Kosten passend klein
        self.e.DATEN_ORDNER = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def engine(self, kerzen, h1, jetzt):
        def holen(symbol, tf, anzahl):
            return symbol, 2, "Test", (h1 if tf == "H1" else kerzen)
        return TradingEngine(self.e, holen, melden=self.meldungen.append, ordner=self.tmp.name)

    def test_eroeffnet_paper_trade_mit_begruendung(self):
        k = kerzen_aus(long_reihe() + [long_reihe()[-1]], DIENSTAG_10_UHR)
        h1 = kerzen_aus([100 + i * 0.8 for i in range(250)], DIENSTAG_10_UHR, 3600, 0.5)
        self.e.TRADER_MIN_CONFIDENCE = 0
        eng = self.engine(k, h1, DIENSTAG_10_UHR)
        eng.schritt(DIENSTAG_10_UHR + 60)
        d = eng.status_daten()
        self.assertEqual(len(d["offene"]), 1, d["entscheidungen"])
        self.assertEqual(d["entscheidungen"][0]["aktion"], "BUY")
        self.assertIn("PAPER-TRADE eröffnet", d["entscheidungen"][0]["gruende"][0])
        self.assertTrue(any("Paper-Trade eröffnet" in m for m in self.meldungen))
        # gleiche Kerze nochmal: keine doppelte Order
        eng.schritt(DIENSTAG_10_UHR + 120)
        self.assertEqual(len(eng.konto.zustand["offene"]), 1)
        # Not-Aus schließt alles und stoppt
        self.assertIn("NOT-AUS", eng.steuern("notaus"))
        self.assertEqual(eng.konto.zustand["offene"], [])
        self.assertEqual(eng.status, "notaus")
        protokoll = (Path(self.tmp.name) / "trader_entscheidungen.jsonl").read_text(encoding="utf-8")
        self.assertIn("BUY", protokoll)

    def test_veraltete_daten_werden_nicht_gehandelt(self):
        alt = DIENSTAG_10_UHR - 3 * 3600
        k = kerzen_aus(long_reihe(), alt)
        h1 = kerzen_aus([100 + i * 0.8 for i in range(250)], alt, 3600)
        eng = self.engine(k, h1, DIENSTAG_10_UHR)
        eng.schritt(DIENSTAG_10_UHR)
        self.assertEqual(eng.konto.zustand["offene"], [])
        self.assertIn("veralteten", eng.status_daten()["entscheidungen"][0]["gruende"][0])

    def test_stufe_0_meldet_nur(self):
        self.e.TRADER_STUFE = 0
        self.e.TRADER_MIN_CONFIDENCE = 0
        k = kerzen_aus(long_reihe() + [long_reihe()[-1]], DIENSTAG_10_UHR)
        h1 = kerzen_aus([100 + i * 0.8 for i in range(250)], DIENSTAG_10_UHR, 3600, 0.5)
        eng = self.engine(k, h1, DIENSTAG_10_UHR)
        eng.schritt(DIENSTAG_10_UHR + 60)
        self.assertEqual(eng.konto.zustand["offene"], [])
        self.assertTrue(any("Trading-Signal" in m for m in self.meldungen))

    def test_hohe_stufen_sind_gesperrt(self):
        self.e.TRADER_STUFE = 3
        eng = self.engine([], [], DIENSTAG_10_UHR)
        self.assertEqual(eng.stufe, 1)  # echtes Geld ist in dieser Version nicht möglich

    def test_drawdown_sperrt_den_roboter(self):
        eng = self.engine([], [], DIENSTAG_10_UHR)
        eng.konto.zustand.update({"balance": 9300, "hoechststand": 10000})
        eng._drawdown_pruefen()
        self.assertEqual(eng.status, "gesperrt")
        self.assertIn("gesperrt", eng.steuern("fortsetzen"))
        status = json.loads((Path(self.tmp.name) / "trader_status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "gesperrt")   # bleibt nach Neustart gesperrt


if __name__ == "__main__":
    unittest.main()
