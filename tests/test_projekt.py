"""
Automatische Tests. Sie prüfen die Rechenlogik mit selbst ausgedachten Beispiel-Trades,
ganz ohne Internet. Starten mit:
    python -m unittest discover tests
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analyse  # noqa: E402
import bericht  # noqa: E402
import datenbank  # noqa: E402
import hyperliquid_api  # noqa: E402

STUNDE = 60 * 60 * 1000


def api_fill(tid, coin, seite, menge, preis, zeit, start, richtung, pnl=0.0, gebuehr=0.0):
    """Baut einen Fill genau so, wie ihn die Hyperliquid-API liefert (Zahlen als Text)."""
    return {"tid": tid, "oid": tid, "coin": coin, "side": seite, "sz": str(menge),
            "px": str(preis), "time": zeit, "startPosition": str(start), "dir": richtung,
            "closedPnl": str(pnl), "fee": str(gebuehr), "hash": f"0x{tid}"}


# Beispiel: BTC Long gewinnt, ETH Short verliert, SOL dreht von Long auf Short
BEISPIEL = [
    api_fill(1, "BTC", "B", 1, 100_000, 0 * STUNDE, 0, "Open Long", gebuehr=10),
    api_fill(2, "BTC", "A", 0.5, 101_000, 1 * STUNDE, 1, "Close Long", pnl=500, gebuehr=5),
    api_fill(3, "BTC", "A", 0.5, 102_000, 2 * STUNDE, 0.5, "Close Long", pnl=1000, gebuehr=5),
    api_fill(4, "ETH", "A", 10, 4000, 3 * STUNDE, 0, "Open Short"),
    api_fill(5, "ETH", "B", 10, 4100, 7 * STUNDE, -10, "Close Short", pnl=-1000),
    api_fill(6, "SOL", "B", 5, 200, 8 * STUNDE, 0, "Open Long"),
    api_fill(7, "SOL", "A", 10, 210, 9 * STUNDE, 5, "Long > Short", pnl=50),
    api_fill(8, "@107", "B", 100, 1, 9 * STUNDE, 0, "Buy"),  # Spot -> wird bei Trades ignoriert
]


class TestAnalyse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = datenbank.verbinden(Path(self.tmp.name) / "test.db")
        self.wallet = "0xabc0000000000000000000000000000000000def"
        datenbank.speichere_fills(self.db, self.wallet, BEISPIEL)
        self.fills = datenbank.fills_von(self.db, self.wallet)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_doppelte_fills_werden_nicht_doppelt_gespeichert(self):
        neu = datenbank.speichere_fills(self.db, self.wallet, BEISPIEL)
        self.assertEqual(neu, 0)
        self.assertEqual(len(datenbank.fills_von(self.db, self.wallet)), len(BEISPIEL))

    def test_trades_werden_richtig_zusammengebaut(self):
        trades, offen = analyse.baue_trades(self.fills)
        self.assertEqual([(t["coin"], t["richtung"]) for t in trades],
                         [("BTC", "Long"), ("ETH", "Short"), ("SOL", "Long")])
        self.assertAlmostEqual(trades[0]["pnl"], 1500 - 20)       # Gewinn minus Gebühren
        self.assertEqual(trades[0]["ende"] - trades[0]["start"], 2 * STUNDE)
        self.assertEqual(len(offen), 1)                           # SOL Short läuft noch
        self.assertEqual(offen[0]["richtung"], "Short")

    def test_kennzahlen(self):
        positionen = [{"coin": "SOL", "groesse": -5, "positionswert": 1000, "hebel": 10},
                      {"coin": "BTC", "groesse": 1, "positionswert": 3000, "hebel": 2}]
        s = analyse.werte_aus(self.fills, positionen, kontowert=2000)
        self.assertEqual(s["anzahl_trades"], 3)
        self.assertAlmostEqual(s["gewinnrate"], 2 / 3)
        self.assertEqual(s["groesster_verlust"]["coin"], "ETH")
        self.assertAlmostEqual(s["groesster_verlust"]["pnl"], -1000)
        self.assertEqual(s["lieblings_coins"][0][0], "BTC")
        self.assertAlmostEqual(s["hebel_schnitt"], (10 * 1000 + 2 * 3000) / 4000)
        self.assertEqual(s["hebel_max"], 10)
        self.assertAlmostEqual(s["hebel_effektiv"], 2.0)
        self.assertAlmostEqual(s["haltedauer_schnitt_ms"], (2 + 4 + 1) * STUNDE / 3)

    def test_position_vor_datenbeginn(self):
        # Der erste Fill schließt eine Position, deren Anfang wir nicht kennen
        fills = [{"coin": "BTC", "seite": "A", "menge": 1, "preis": 1, "zeit": 5,
                  "start_position": 1, "richtung": "Close Long", "closed_pnl": 200, "gebuehr": 0}]
        trades, _ = analyse.baue_trades(fills)
        self.assertFalse(trades[0]["vollstaendig"])
        s = analyse.werte_aus(fills)
        self.assertIsNone(s["haltedauer_schnitt_ms"])  # Haltedauer unbekannt
        self.assertEqual(s["gewinnrate"], 1.0)         # Ergebnis zählt trotzdem

    def test_einigkeit(self):
        kauf = {"BTC": {"gekauft": 100, "verkauft": 0, "netto": 100}}
        verkauf = {"BTC": {"gekauft": 0, "verkauft": 50, "netto": -50}}
        ergebnis = analyse.einigkeit({"a": kauf, "b": kauf, "c": kauf, "d": verkauf}, 3, 0.7)
        self.assertEqual(ergebnis[0]["einig"], "KAUFEN")         # 3 von 4 = 75 %
        ergebnis = analyse.einigkeit({"a": kauf, "b": kauf, "c": verkauf}, 3, 0.7)
        self.assertIsNone(ergebnis[0]["einig"])                  # 2 von 3 = 67 %

    def test_bericht_wird_erstellt(self):
        top = [{"wallet": self.wallet, "name": None, "rang": 1, "kontowert": 2000,
                "pnl_tag": 1, "pnl_woche": 2, "pnl_monat": 12345, "pnl_gesamt": 4,
                "roi_monat": 0.1, "volumen_monat": 5}]
        datenbank.speichere_top_trader(self.db, top)
        text = bericht.erstelle_bericht(self.db, jetzt_ms=10 * STUNDE, min_trader=1, min_anteil=0.7)
        self.assertIn("Tagesbericht", text)
        self.assertIn("+12.345 $", text)
        self.assertIn("| BTC |", text)


class TestApi(unittest.TestCase):
    def test_rangliste_und_auswahl(self):
        antwort = {"leaderboardRows": [
            {"ethAddress": "0xAAA", "accountValue": "50000", "displayName": None,
             "windowPerformances": [["month", {"pnl": "100", "roi": "0.1", "vlm": "1"}]]},
            {"ethAddress": "0xBBB", "accountValue": "50000", "displayName": "Profi",
             "windowPerformances": [["month", {"pnl": "900", "roi": "0.2", "vlm": "1"}]]},
            {"ethAddress": "0xCCC", "accountValue": "5", "displayName": None,
             "windowPerformances": [["month", {"pnl": "99999", "roi": "9", "vlm": "1"}]]},
        ]}
        with mock.patch.object(hyperliquid_api, "_anfrage", return_value=antwort):
            rangliste = hyperliquid_api.lade_rangliste()
        top = hyperliquid_api.waehle_top_trader(rangliste, 2, "month", min_kontowert=10_000)
        self.assertEqual([t["wallet"] for t in top], ["0xbbb", "0xaaa"])  # 0xCCC: zu wenig Geld
        self.assertEqual(top[0]["rang"], 1)

    def test_fills_werden_seitenweise_geladen(self):
        seite1 = [{"time": i} for i in range(2000)]
        seite2 = [{"time": 1999 + i} for i in range(10)]
        with mock.patch.object(hyperliquid_api, "_anfrage", side_effect=[seite1, seite2]) as m:
            fills = hyperliquid_api.lade_fills("0xabc")
        self.assertEqual(len(fills), 2010)
        self.assertEqual(m.call_args_list[1].args[1]["startTime"], 1999)


if __name__ == "__main__":
    unittest.main()
