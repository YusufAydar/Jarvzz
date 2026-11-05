"""
Tests für die Trading-Analyse – ohne MetaTrader 5.
MT5 wird hier durch einen Platzhalter ersetzt, die Kurse sind ausgedachte Testreihen.
"""

import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import einstellungen  # noqa: E402
import termine  # noqa: E402
import werkzeuge  # noqa: E402
from trading import indikatoren as ind  # noqa: E402
from trading import mt5_verbindung as mt  # noqa: E402


def kerzen_aus(schluss, spanne=0.5):
    return [{"zeit": i, "open": c, "high": c + spanne, "low": c - spanne, "close": c}
            for i, c in enumerate(schluss)]


class TestIndikatoren(unittest.TestCase):
    def test_ema_konstante_reihe(self):
        self.assertAlmostEqual(ind.ema([5.0] * 30, 10)[-1], 5.0)
        self.assertIsNone(ind.ema([1, 2, 3], 10)[-1])

    def test_rsi_extremwerte(self):
        self.assertEqual(ind.rsi(list(range(1, 40)))[-1], 100.0)        # nur Gewinne
        self.assertLess(ind.rsi(list(range(40, 1, -1)))[-1], 1.0)       # nur Verluste
        zickzack = [100 + (1 if i % 2 else -1) for i in range(60)]
        self.assertAlmostEqual(ind.rsi(zickzack)[-1], 50, delta=5)      # ausgeglichen

    def test_atr_konstante_spanne(self):
        self.assertAlmostEqual(ind.atr(kerzen_aus([100.0] * 40, spanne=0.5))[-1], 1.0)

    def test_trend(self):
        self.assertEqual(ind.trend(kerzen_aus([100 + i * 0.5 for i in range(120)])), "Aufwärtstrend")
        self.assertEqual(ind.trend(kerzen_aus([200 - i * 0.5 for i in range(120)])), "Abwärtstrend")
        welle = [100 + 3 * math.sin(i / 4) for i in range(120)]
        self.assertEqual(ind.trend(kerzen_aus(welle)), "Seitwärts")

    def test_preiszonen_finden_wendepunkte(self):
        # Kurs pendelt zwischen ~90 und ~110 und steht jetzt bei 100
        welle = [100 + 10 * math.sin(i / 5) for i in range(150)] + [100]
        unter, ueber = ind.preiszonen(kerzen_aus(welle, spanne=0.2))
        self.assertTrue(unter and ueber)
        self.assertAlmostEqual(unter[0][0], 90, delta=1.5)
        self.assertAlmostEqual(ueber[0][0], 110, delta=1.5)
        self.assertGreaterEqual(unter[0][1], 3)  # mehrfach berührt

    def test_pivots(self):
        p = ind.pivot_punkte({"high": 110, "low": 90, "close": 100})
        self.assertEqual((p["PP"], p["R1"], p["S1"], p["R2"], p["S2"]), (100, 110, 90, 120, 80))

    def test_macd_kreuzung_erkannt(self):
        # langer Abwärtstrend, dann zwei kräftige Kerzen nach oben -> frische Kreuzung
        reihe = [100 - i * 0.3 for i in range(80)] + [76 + i * 1.5 for i in range(2)]
        a = ind.analysiere(kerzen_aus(reihe))
        self.assertEqual(a["macd_kreuzung"], "nach oben")

    def test_zusammenfassung_ist_lesbar(self):
        a = ind.analysiere(kerzen_aus([100 + i * 0.5 for i in range(120)]),
                           vortag={"high": 110, "low": 90, "close": 100})
        text = ind.zusammenfassung("EURUSD", "M15", a, 2)
        for wort in ("Aufwärtstrend", "RSI", "MACD", "ATR", "Tages-Pivots"):
            self.assertIn(wort, text)


class TestFtmo(unittest.TestCase):
    def test_ampel_und_restbetraege(self):
        konto = {"equity": 9800}
        p = mt.ftmo_pruefung(konto, start_heute=10000, kontogroesse=10000)
        self.assertEqual(p["ampel"], "gelb")                      # 200 von 300 erlaubten heute
        self.assertAlmostEqual(p["rest_tagesverlust_sicher"], 100)
        self.assertAlmostEqual(p["rest_tagesverlust_ftmo"], 300)
        self.assertEqual(mt.ftmo_pruefung({"equity": 9650}, 10000, 10000)["ampel"], "rot")
        self.assertEqual(mt.ftmo_pruefung({"equity": 10500}, 10000, 10000)["ampel"], "grün")
        self.assertAlmostEqual(mt.ftmo_pruefung({"equity": 10500}, 10000, 10000)["fortschritt_ziel_prozent"], 50)

    def test_tagesstart_wird_pro_tag_gemerkt(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "tagesstart.json"
            self.assertEqual(mt.tagesstart_balance(10000, datei), 10000)
            self.assertEqual(mt.tagesstart_balance(9500, datei), 10000)  # gleicher Tag: bleibt


class FakeMT5:
    """Tut so, als wäre MetaTrader 5 geöffnet."""
    TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_D1 = 15, 60, 1440

    def terminal_info(self):
        return object()

    def symbol_select(self, name, an=True):
        return name in ("EURUSD", "US30.cash")

    def symbols_get(self, muster):
        return [SimpleNamespace(name="US30.cash")] if "US30" in muster else []

    def copy_rates_from_pos(self, symbol, tf, start, anzahl):
        return [{"time": i, "open": 1.1 + i * 1e-4, "high": 1.1 + i * 1e-4 + 5e-4,
                 "low": 1.1 + i * 1e-4 - 5e-4, "close": 1.1 + i * 1e-4} for i in range(anzahl)]

    def symbol_info(self, symbol):
        return SimpleNamespace(digits=5)

    def account_info(self):
        return SimpleNamespace(login=123, server="FTMO-Demo", currency="USD",
                               balance=10000.0, equity=9900.0, profit=-100.0)

    def positions_get(self):
        return [SimpleNamespace(symbol="EURUSD", type=0, volume=0.5, price_open=1.1, sl=0.0, tp=0.0, profit=-100.0)]

    def last_error(self):
        return (0, "ok")

    def shutdown(self):
        pass


class TestWerkzeuge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kasten = werkzeuge.Werkzeugkasten(termine.Terminkalender(Path(self.tmp.name) / "t.json"))
        mt._symbol_cache.clear()
        self.patches = [mock.patch.object(mt, "mt5", FakeMT5()),
                        mock.patch.object(einstellungen, "DATEN_ORDNER", Path(self.tmp.name))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_symbol_wird_beim_broker_gefunden(self):
        self.assertEqual(mt.symbol_finden("Dow"), "US30.cash")
        self.assertEqual(mt.symbol_finden("eurusd"), "EURUSD")

    def test_markt_analyse(self):
        text = self.kasten.ausfuehren("markt_analyse", {"symbol": "EURUSD"})
        self.assertIn("EURUSD (M15)", text)
        self.assertIn("Trend H1", text)
        self.assertIn("Tages-Pivots", text)

    def test_konto_status_warnt_bei_fehlendem_stop_loss(self):
        text = self.kasten.ausfuehren("konto_status", {})
        self.assertIn("Equity 9900.00 USD", text)
        self.assertIn("SL KEINER", text)

    def test_mt5_zugang_speichern(self):
        env = Path(self.tmp.name) / ".env"
        env.write_text("ANTHROPIC_API_KEY=sk-ant-geheim\nMT5_LOGIN=111\n", encoding="utf-8")
        gefragt = []
        self.kasten.bestaetigen = lambda art, beschreibung, details: (gefragt.append(beschreibung + details), True)[1]
        with mock.patch.object(einstellungen, "JARVIS_ORDNER", Path(self.tmp.name)), \
             mock.patch.dict("os.environ", {}, clear=False):
            text = self.kasten.ausfuehren("mt5_zugang_speichern",
                                          {"login": "1515", "passwort": "Pw!123", "server": "FTMO-Demo"})
        inhalt = env.read_text(encoding="utf-8")
        self.assertIn("ANTHROPIC_API_KEY=sk-ant-geheim", inhalt)   # API-Schlüssel bleibt
        self.assertIn("MT5_LOGIN=1515", inhalt)
        self.assertNotIn("MT5_LOGIN=111", inhalt)                    # alter Eintrag ersetzt
        self.assertIn("MT5_PASSWORT=Pw!123", inhalt)
        self.assertIn("verbunden mit Konto 123", text)
        self.assertNotIn("Pw!123", text + "".join(gefragt))          # Passwort wird nirgends angezeigt

    def test_mt5_wird_nicht_selbst_gestartet(self):
        fake = FakeMT5()
        fake.terminal_info = lambda: None                 # MT5 ist nicht verbunden ...
        fake.initialize = mock.Mock(return_value=True)
        with mock.patch.object(mt, "mt5", fake), mock.patch.object(mt, "mt5_laeuft", return_value=False):
            with self.assertRaises(mt.MT5Fehler) as fehler:  # ... und nicht geöffnet
                mt.verbinden()
        self.assertIn("nicht geöffnet", str(fehler.exception))
        fake.initialize.assert_not_called()               # also wird es auch nicht gestartet

    def test_ohne_mt5_klare_meldung(self):
        with mock.patch.object(mt, "mt5", None):
            self.assertIn("MetaTrader5 fehlt", self.kasten.ausfuehren("konto_status", {}))


if __name__ == "__main__":
    unittest.main()
