"""Tests für die Muster-Auswertung der Top-Trader (ohne Internet)."""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import muster  # noqa: E402

H = muster.STUNDE_MS


def kerzen_aufwaerts(anzahl=120, start=0):
    return [{"zeit": start + i * H, "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i}
            for i in range(anzahl)]


class TestMuster(unittest.TestCase):
    def test_marktlage_ausbruch_mit_trend(self):
        k = kerzen_aufwaerts()
        k[-1] = dict(k[-1], close=k[-1]["high"] + 3, high=k[-1]["high"] + 3)   # Schluss über dem 20-Stunden-Hoch
        self.assertEqual(muster.marktlage(k, "Long"), ("mit dem Trend", "Ausbruch"))
        trend, _ = muster.marktlage(kerzen_aufwaerts(), "Short")
        self.assertEqual(trend, "gegen den Trend")

    def test_marktlage_pullback(self):
        k = kerzen_aufwaerts()
        for _ in range(20):  # Rücksetzer bis an die EMA20 (die EMA bewegt sich mit, daher mehrmals angleichen)
            e20 = muster.ema([x["close"] for x in k], 20)[-1]
            for i in range(1, 4):
                k[-i] = dict(k[-i], close=e20 + 0.2, high=e20 + 1, low=e20 - 0.5)
        self.assertEqual(muster.marktlage(k, "Long")[1], "Pullback")

    def test_zu_wenig_kerzen(self):
        self.assertEqual(muster.marktlage(kerzen_aufwaerts(30), "Long"), ("unbekannt", "unbekannt"))

    def test_sitzung_und_haltedauer(self):
        self.assertIn("London", muster.sitzung(10))
        self.assertIn("New York", muster.sitzung(19))
        self.assertIn("Daytrading", muster.haltedauer_text(2 * H))
        self.assertIn("Scalping", muster.haltedauer_text(5 * 60000))

    def test_auswertung_und_bericht(self):
        start = int(datetime(2026, 11, 3, 15, 0).timestamp() * 1000)
        kerzen = {"BTC": kerzen_aufwaerts(200, start - 150 * H)}
        trades = {}
        for w in range(4):   # 4 Trader mit je 6 Trades -> 24 Trades, genug für ein Muster
            trades[f"w{w}"] = [{"coin": "BTC", "richtung": "Long", "start": start + i * H, "ende": start + i * H + 2 * H,
                                "pnl": 100.0 if i % 3 else -50.0, "vollstaendig": True} for i in range(6)]
        tabelle = muster.auswerten(trades, kerzen)
        self.assertEqual(sum(z["trades"] for z in tabelle["Richtung"].values()), 24)
        gut, _ = muster.erkenntnisse(tabelle)
        self.assertTrue(gut)
        text = muster.bericht(tabelle, 4, 24, "Test")
        self.assertIn("Was bei den Profis Geld bringt", text)
        self.assertIn("keine Trades kopiert", text)


if __name__ == "__main__":
    unittest.main()
