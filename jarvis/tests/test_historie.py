"""Tests für den Dukascopy-Download (Dateien im echten Format nachgebaut, ohne Internet)."""

import io
import lzma
import struct
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trading import historie  # noqa: E402


def bi5(kerzen):
    """Baut eine Dukascopy-Tagesdatei: (sekunde, open, close, low, high, volumen) als ganze Zahlen."""
    roh = b"".join(struct.pack(">IIIIIf", *k) for k in kerzen)
    return lzma.compress(roh, format=lzma.FORMAT_ALONE)


class TestHistorie(unittest.TestCase):
    def test_entpacken_und_leere_kerzen_weglassen(self):
        daten = bi5([(0, 2400000, 2401000, 2399000, 2402000, 1.5), (60, 2401000, 2401500, 2400500, 2402000, 0.0)])
        k = historie.kerzen_aus_bi5(daten, 1000)
        self.assertEqual(len(k), 1)                       # Kerze ohne Volumen = Markt zu
        self.assertEqual((k[0]["zeit"], k[0]["close"]), (1000, 2401000))
        self.assertEqual(historie.kerzen_aus_bi5(b"", 0), [])

    def test_preis_faktor_erkennen(self):
        gold = [{"close": 2400123}]
        euro = [{"close": 108345}]
        self.assertEqual(historie.faktor_finden(gold, (300, 20000)), 1000)
        self.assertEqual(historie.faktor_finden(euro, (0.5, 2.5)), 100000)

    def test_m15_buendeln(self):
        k = [{"zeit": i * 60, "open": i, "high": i + 1, "low": i - 1, "close": i} for i in range(30)]
        m15 = historie.zu_m15(k)
        self.assertEqual(len(m15), 2)
        self.assertEqual((m15[0]["open"], m15[0]["high"], m15[0]["low"], m15[0]["close"]), (0, 15, -1, 14))

    def test_tag_laden_und_zwischenspeichern(self):
        tag = date(2025, 3, 4)
        daten = bi5([(m * 60, 108300 + m, 108310 + m, 108290 + m, 108320 + m, 1.0) for m in range(60)])
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(historie.urllib.request, "urlopen", return_value=io.BytesIO(daten)) as netz:
            netz.return_value.__enter__ = lambda s: s
            netz.return_value.__exit__ = lambda *a: None
            m15 = historie._tag_laden("EURUSD", tag, (0.5, 2.5), Path(tmp))
            self.assertIn("EURUSD/2025/02/04/", netz.call_args.args[0].full_url)   # Monat ist 0-basiert
            self.assertEqual(len(m15), 4)
            self.assertAlmostEqual(m15[0]["open"], 1.083, places=5)
            start = int(datetime(2025, 3, 4, tzinfo=timezone.utc).timestamp())
            self.assertEqual(m15[0]["zeit"], start)
            zweiter = historie._tag_laden("EURUSD", tag, (0.5, 2.5), Path(tmp))   # aus dem Speicher
            self.assertEqual(netz.call_count, 1)
            self.assertEqual(zweiter, m15)

    def test_unbekanntes_symbol(self):
        with self.assertRaises(ValueError):
            historie.m15_laden("FANTASIE", 5)

    def test_laden_ueber_mehrere_tage_in_richtiger_reihenfolge(self):
        def tag_laden(sym, tag, bereich, ordner, nur_gespeichert=False):
            t = int(datetime(tag.year, tag.month, tag.day, tzinfo=timezone.utc).timestamp())
            return [{"zeit": t, "open": 1, "high": 1, "low": 1, "close": 1}]
        with mock.patch.object(historie, "_tag_laden", side_effect=tag_laden):
            k = historie.m15_laden("EURUSD", 14)
        zeiten = [x["zeit"] for x in k]
        self.assertEqual(zeiten, sorted(zeiten))
        self.assertEqual(len(k), 12)   # 14 Tage ohne 2 Samstage

    def test_zweiter_versuch_und_fehlertoleranz(self):
        versuche = {}

        def tag_laden(sym, tag, bereich, ordner, nur_gespeichert=False):
            versuche[tag] = versuche.get(tag, 0) + 1
            if tag.day % 3 == 0 and versuche[tag] == 1:   # erster Versuch scheitert, zweiter klappt
                raise ConnectionError("gedrosselt")
            return [{"zeit": tag.toordinal(), "open": 1, "high": 1, "low": 1, "close": 1}]
        with mock.patch.object(historie, "_tag_laden", side_effect=tag_laden), \
                mock.patch.object(historie.time, "sleep"):
            historie.m15_laden("EURUSD", 30)
        self.assertTrue(any(v == 2 for v in versuche.values()))

    def test_nur_gespeichert_laedt_nichts_herunter(self):
        with tempfile.TemporaryDirectory() as ordner, \
                mock.patch.object(historie.urllib.request, "urlopen") as netz:
            info = {}
            with self.assertRaises(ValueError):
                historie.m15_laden("EURUSD", 20, ordner=ordner, nur_gespeichert=True, info=info)
            self.assertFalse(netz.called)
            self.assertGreater(info["fehlend"], 10)


if __name__ == "__main__":
    unittest.main()
