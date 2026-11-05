"""Tests für TradingView-Analyse, Kursquellen, Kalender, Setup-Scanner, Positionsgröße und Alarme.
Alles ohne Internet: Die Antworten der Dienste werden im echten Format nachgebaut."""

import math
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import einstellungen  # noqa: E402
import termine  # noqa: E402
import werkzeuge  # noqa: E402
from trading import alarme, kalender, kursquellen, setups, tradingview  # noqa: E402


def kerzen_aus(schluss, spanne=0.3, start=1_700_000_000, schritt=900):
    return [{"zeit": start + i * schritt, "open": c, "high": c + spanne, "low": c - spanne, "close": c}
            for i, c in enumerate(schluss)]


class TestKursquellen(unittest.TestCase):
    def test_yahoo_antwort_auswerten(self):
        daten = {"chart": {"result": [{"timestamp": [0, 3600, 7200, 10800, 14400],
                                       "indicators": {"quote": [{"open": [1, 2, None, 4, 5], "high": [2, 3, None, 5, 6],
                                                                 "low": [0, 1, None, 3, 4], "close": [2, 3, None, 5, 6]}]}}]}}
        k = kursquellen.yahoo_auswerten(daten)
        self.assertEqual(len(k), 4)  # Lücke übersprungen
        h4 = kursquellen.yahoo_auswerten(daten, buendeln=4)
        self.assertEqual(len(h4), 2)
        self.assertEqual((h4[0]["open"], h4[0]["high"], h4[0]["low"], h4[0]["close"]), (1, 5, 0, 5))

    def test_kuerzel(self):
        self.assertEqual(kursquellen.yahoo_kuerzel("Gold"), "GC=F")
        self.assertEqual(kursquellen.tradingview_kuerzel("US30.cash"), "OANDA:US30USD")
        self.assertEqual(kursquellen.tradingview_kuerzel("nasdaq:aapl"), "NASDAQ:AAPL")
        self.assertIsNone(kursquellen.yahoo_kuerzel("Fantasie"))


class TestTradingView(unittest.TestCase):
    def antwort(self, gesamt):
        tfs = ("M15", "H1")
        spalten = tradingview.spalten_fuer(tfs)
        werte = []
        for s in spalten:
            if s.startswith("Recommend"):
                werte.append(gesamt)
            elif s.startswith("MACD.macd"):
                werte.append(1.0)
            else:
                werte.append(50.0)
        return {"data": [{"s": "OANDA:XAUUSD", "d": werte}], "totalCount": 1}, tfs

    def test_bewertung(self):
        self.assertEqual(tradingview.bewertung(0.6), "STARK KAUFEN")
        self.assertEqual(tradingview.bewertung(0.0), "NEUTRAL")
        self.assertEqual(tradingview.bewertung(-0.3), "VERKAUFEN")

    def test_auswerten_und_einigkeit(self):
        antwort, tfs = self.antwort(0.7)
        e = tradingview.auswerten(antwort, tfs)
        self.assertEqual(e["ticker"], "OANDA:XAUUSD")
        self.assertEqual(e["zeitrahmen"]["H1"]["Recommend.All"], 0.7)
        text = tradingview.zusammenfassung("Gold", e)
        self.assertIn("STARK KAUFEN", text)
        self.assertIn("Alle Zeitrahmen zeigen KAUFEN", text)
        self.assertIsNone(tradingview.auswerten({"data": []}, tfs))

    def test_verkaufen_ist_nicht_kaufen(self):
        # Fehler aus dem Live-Check: "VERKAUFEN" enthält "KAUFEN" -> wurde als "Richtung nach oben" gemeldet
        antwort, tfs = self.antwort(-0.7)
        text = tradingview.zusammenfassung("US30", tradingview.auswerten(antwort, tfs))
        self.assertIn("Alle Zeitrahmen zeigen VERKAUFEN", text)
        self.assertNotIn("nach oben", text)

    def test_tageswerte_ohne_suffix(self):
        spalten = tradingview.spalten_fuer(("D1",))
        self.assertIn("Recommend.All", spalten)
        self.assertIn("RSI", spalten)


class TestKalender(unittest.TestCase):
    def test_filter(self):
        jetzt = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        daten = [
            {"title": "Non-Farm Payrolls", "country": "USD", "date": "2026-11-05T08:30:00-05:00", "impact": "High",
             "forecast": "120K", "previous": "98K"},
            {"title": "Retail Sales", "country": "EUR", "date": "2026-11-05T10:00:00+01:00", "impact": "Medium"},
            {"title": "Alt", "country": "USD", "date": "2026-11-01T08:30:00-05:00", "impact": "High"},
        ]
        wichtig = kalender.termine(daten, jetzt - timedelta(hours=12), jetzt + timedelta(days=1))
        self.assertEqual([e["titel"] for e in wichtig], ["Non-Farm Payrolls"])
        alle = kalender.termine(daten, jetzt - timedelta(hours=12), jetzt + timedelta(days=1), nur_wichtig=False)
        self.assertEqual(len(alle), 2)
        self.assertIn("Prognose 120K", kalender.zusammenfassung(wichtig, "News"))


def long_setup_kerzen():
    """Aufwärtstrend, Rücksetzer an die EMA20, dann drehen RSI und MACD wieder nach oben."""
    reihe = [100 + i * 0.3 for i in range(150)]                 # Trend
    reihe += [reihe[-1] - j * 0.3 for j in range(1, 9)]           # Rücksetzer
    tief = reihe[-1]
    reihe += [tief + 0.3, tief + 0.6]                             # zwei grüne Kerzen: Schwung dreht
    return kerzen_aus(reihe)


class TestSetups(unittest.TestCase):
    def test_long_setup_wird_gefunden(self):
        kerzen = long_setup_kerzen()
        h1 = kerzen_aus([100 + i * 0.8 for i in range(120)], spanne=0.5, schritt=3600)
        e = setups.finde_setup(kerzen, h1, "TEST", 2)
        self.assertIsNotNone(e["setup"], e.get("grund"))
        s = e["setup"]
        self.assertEqual(s["richtung"], "LONG")
        self.assertLess(s["stop"], s["einstieg"])
        self.assertGreater(s["ziel"], s["einstieg"])
        self.assertGreaterEqual(s["crv"], 1.5)
        self.assertIn("LONG-SETUP", setups.setup_text(e, 2))

    def test_kein_setup_ohne_trend(self):
        welle = kerzen_aus([100 + (1 if i % 2 else -1) for i in range(200)])
        h1 = kerzen_aus([100 + (1 if i % 2 else -1) for i in range(120)], schritt=3600)
        e = setups.finde_setup(welle, h1, "TEST")
        self.assertIsNone(e["setup"])
        self.assertIn("kein klarer Trend", e["grund"])

    def test_kein_hinterherrennen(self):
        steil = kerzen_aus([100 + i * 0.8 for i in range(160)])  # nie zurückgekommen
        h1 = kerzen_aus([100 + i * 0.8 for i in range(120)], schritt=3600)
        e = setups.finde_setup(steil, h1, "TEST")
        self.assertIsNone(e["setup"])
        self.assertIn("nicht an EMA/Zone zurückgekommen", e["grund"])

    def test_positionsgroesse(self):
        # Gold: 100 Unzen pro Lot -> 1 $ Bewegung = 100 $ pro Lot. 0,5 % von 10.000 = 50 $, Stop 2 $ entfernt
        r = setups.positionsgroesse(10000, 0.5, 2400, 2398, wert_pro_punkt_und_lot=100)
        self.assertEqual(r["lots"], 0.25)
        self.assertLessEqual(r["tatsaechliches_risiko"], 50)
        r2 = setups.positionsgroesse(10000, 0.5, 2400, 2398, symbol="XAUUSD")
        self.assertIn("Standard", r2["quelle"])
        self.assertIsNone(setups.positionsgroesse(10000, 0.5, 100, 99, symbol="US30")["lots"])
        with self.assertRaises(ValueError):
            setups.positionsgroesse(10000, 0.5, 100, 100, 1)


class TestAlarme(unittest.TestCase):
    def test_preis_und_rsi_alarm(self):
        preise = {"wert": 100.0}

        def kerzen_holen(symbol, tf, anzahl):
            return symbol, 2, "Test", kerzen_aus([preise["wert"]] * 30 + [preise["wert"] + i for i in range(1, 31)])

        with tempfile.TemporaryDirectory() as tmp:
            a = alarme.Alarme(Path(tmp) / "alarme.json", kerzen_holen)
            a.hinzufuegen("GOLD", "preis_ueber", 200)
            a.hinzufuegen("GOLD", "rsi_ueber", 70)
            meldungen = a.pruefen()
            self.assertEqual(len(meldungen), 1)          # nur der RSI-Alarm (Preis noch unter 200)
            self.assertIn("RSI", meldungen[0])
            preise["wert"] = 250.0
            self.assertIn("über 200", a.pruefen()[0])
            self.assertEqual(a.aktive(), [])             # beide erledigt
            self.assertEqual(len(alarme.Alarme(Path(tmp) / "alarme.json", kerzen_holen).liste), 2)  # gespeichert

    def test_falsche_eingaben(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = alarme.Alarme(Path(tmp) / "x.json", None)
            with self.assertRaises(ValueError):
                a.hinzufuegen("GOLD", "mondphase", 1)
            with self.assertRaises(ValueError):
                a.hinzufuegen("GOLD", "preis_ueber")


class TestWerkzeuge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(einstellungen, "DATEN_ORDNER", Path(self.tmp.name))
        self.patch.start()
        self.kasten = werkzeuge.Werkzeugkasten(termine.Terminkalender(Path(self.tmp.name) / "t.json"))
        self.kasten.melden = lambda text: None

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_alle_neuen_werkzeuge_haben_eine_funktion(self):
        for w in werkzeuge.WERKZEUG_BESCHREIBUNGEN:
            self.assertTrue(hasattr(self.kasten, f"_{w['name']}"), w["name"])

    def test_setup_scanner_ueber_werkzeug(self):
        kerzen = long_setup_kerzen()
        h1 = kerzen_aus([100 + i * 0.8 for i in range(120)], spanne=0.5, schritt=3600)
        with mock.patch("trading.marktdaten.kerzen_holen",
                        side_effect=lambda s, tf, n=300: ("TEST", 2, "Test", h1 if tf == "H1" else kerzen)):
            text = self.kasten.ausfuehren("setup_scanner", {"symbol": "TEST"})
        self.assertIn("LONG-SETUP", text)

    def test_tradingview_offline_klare_meldung(self):
        with mock.patch("trading.tradingview.analyse", side_effect=OSError("kein Netz")):
            self.assertIn("nicht erreichbar", self.kasten.ausfuehren("tradingview_analyse", {"symbol": "Gold"}))
        self.assertIn("BÖRSE:SYMBOL", self.kasten.ausfuehren("tradingview_analyse", {"symbol": "Fantasie"}))

    def test_alarm_setzen_und_verwalten(self):
        with mock.patch("trading.alarme.waechter_starten"):
            self.assertIn("Alarm gesetzt", self.kasten.ausfuehren(
                "alarm_setzen", {"symbol": "GOLD", "art": "preis_unter", "wert": 2300}))
            self.assertIn("Preis unter 2300", self.kasten.ausfuehren("alarme_verwalten", {}))
            self.assertEqual(self.kasten.ausfuehren("alarme_verwalten", {"loeschen_id": 1}), "Gelöscht.")

    def test_positionsgroesse_ohne_mt5(self):
        text = self.kasten.ausfuehren("positionsgroesse_berechnen",
                                      {"symbol": "XAUUSD", "einstieg": 2400, "stop": 2398})
        self.assertIn("Lotgröße: 0.25 Lot", text)


if __name__ == "__main__":
    unittest.main()
