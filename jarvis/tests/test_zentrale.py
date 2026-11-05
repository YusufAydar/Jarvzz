"""Tests für die Trading-Zentrale, das Tagebuch, die Chart-Steuerung, Screenshots und die Verbindung zu Claude."""

import hashlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import einstellungen  # noqa: E402
import gehirn  # noqa: E402
import sync  # noqa: E402
import termine  # noqa: E402
import werkzeuge  # noqa: E402
import zentrale  # noqa: E402
from trading import marktdaten  # noqa: E402
from trading.tagebuch import Tagebuch, auswertung_text  # noqa: E402


class TestTagebuch(unittest.TestCase):
    def test_r_berechnung_und_auswertung(self):
        with tempfile.TemporaryDirectory() as tmp:
            tb = Tagebuch(Path(tmp) / "tb.json")
            e1 = tb.eintragen("xauusd", "long", 4120, 4110, 4140, gewinn=200, notiz="sauber")
            e2 = tb.eintragen("EURUSD", "SHORT", 1.1250, 1.1270, 1.1270, gewinn=-100)
            tb.eintragen("US30", "LONG", notiz="nur Notiz")
            self.assertEqual(e1["r"], 2.0)          # 20 Punkte Gewinn bei 10 Punkten Risiko
            self.assertEqual(e2["r"], -1.0)         # Stop getroffen
            a = tb.auswertung(30)
            self.assertEqual((a["trades"], a["mit_ergebnis"]), (3, 2))
            self.assertAlmostEqual(a["trefferquote"], 0.5)
            self.assertAlmostEqual(a["summe_r"], 1.0)
            self.assertEqual(a["pro_symbol"]["XAUUSD"]["gewonnen"], 1)
            self.assertIn("Trefferquote 50 %", auswertung_text(a))
            self.assertEqual(len(Tagebuch(Path(tmp) / "tb.json").eintraege), 3)  # gespeichert
            with self.assertRaises(ValueError):
                tb.eintragen("X", "seitwärts")


class TestKerzenCache(unittest.TestCase):
    def test_internetquellen_werden_zwischengespeichert(self):
        marktdaten._cache.clear()
        kerzen = [{"zeit": i, "open": 1, "high": 1, "low": 1, "close": 1} for i in range(500)]
        with mock.patch.object(marktdaten.mt, "kerzen", side_effect=marktdaten.mt.MT5Fehler("aus")), \
             mock.patch.object(marktdaten.kursquellen, "yahoo_kerzen", return_value=("GC=F", kerzen)) as y:
            a = marktdaten.kerzen_holen("XAUUSD", "M15", 300)
            b = marktdaten.kerzen_holen("XAUUSD", "M15", 200)
        self.assertEqual(y.call_count, 1)  # zweites Mal aus dem Zwischenspeicher
        self.assertEqual((len(a[3]), len(b[3]), a[2]), (300, 200, "Yahoo Finance"))


class TestWerkzeuge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(einstellungen, "DATEN_ORDNER", Path(self.tmp.name))
        self.p.start()
        self.kasten = werkzeuge.Werkzeugkasten(termine.Terminkalender(Path(self.tmp.name) / "t.json"),
                                               bestaetigen=lambda *a: True)

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_chart_zeigen(self):
        self.assertIn("nicht geöffnet", self.kasten.ausfuehren("chart_zeigen", {"symbol": "Gold"}))
        befehle = []
        self.kasten.ui_befehl = lambda b: befehle.append(b) or True
        text = self.kasten.ausfuehren("chart_zeigen", {"symbol": "XAUUSD", "zeitrahmen": "H1"})
        self.assertIn("XAUUSD auf H1", text)
        self.assertEqual(befehle, [{"aktion": "chart", "symbol": "XAUUSD", "zeitrahmen": "H1"}])

    def test_tagebuch_werkzeuge(self):
        self.assertIn("+2.00 R", self.kasten.ausfuehren("tagebuch_eintragen", {
            "symbol": "Gold", "richtung": "LONG", "einstieg": 100, "stop": 99, "ausstieg": 102}))
        self.assertIn("Trefferquote 100 %", self.kasten.ausfuehren("tagebuch_auswertung", {}))

    def test_bildschirm_ohne_windows(self):
        with mock.patch.object(werkzeuge, "IST_WINDOWS", False), \
             mock.patch.dict(sys.modules, {"PIL": SimpleNamespace(ImageGrab=object())}):
            self.assertIn("nur unter Windows", self.kasten.ausfuehren("bildschirm_ansehen", {}))

    def test_alle_werkzeuge_haben_funktion(self):
        for w in werkzeuge.alle_werkzeuge():
            if w.get("type", "").startswith("web_search"):
                continue
            self.assertTrue(hasattr(self.kasten, f"_{w['name']}"), w["name"])


class TestGehirnBilder(unittest.TestCase):
    def test_screenshot_geht_als_bild_an_claude(self):
        inhalt = gehirn._ergebnis_inhalt({"text": "Screenshot", "bild": "QUJD", "media_type": "image/jpeg"})
        self.assertEqual(inhalt[0]["type"], "image")
        self.assertEqual(inhalt[0]["source"]["data"], "QUJD")
        self.assertEqual(inhalt[1], {"type": "text", "text": "Screenshot"})
        self.assertEqual(gehirn._ergebnis_inhalt("nur Text"), "nur Text")


class TestNewsWaechter(unittest.TestCase):
    def test_warnt_einmal_vor_wichtigen_news(self):
        jetzt = 1_000_000
        liste = [{"zeit": jetzt + 600, "titel": "Non-Farm Payrolls", "waehrung": "USD", "wichtig": "HOCH"},
                 {"zeit": jetzt + 600, "titel": "Kleinkram", "waehrung": "USD", "wichtig": "mittel"},
                 {"zeit": jetzt + 600, "titel": "Zinsentscheid", "waehrung": "JPY", "wichtig": "HOCH"},
                 {"zeit": jetzt + 7200, "titel": "Später", "waehrung": "USD", "wichtig": "HOCH"}]
        gemeldet = set()
        texte = zentrale.news_pruefen(liste, jetzt, gemeldet, 15, ["USD", "EUR"])
        self.assertEqual(len(texte), 1)
        self.assertIn("in 10 Minuten", texte[0])
        self.assertIn("Non-Farm Payrolls", texte[0])
        self.assertEqual(zentrale.news_pruefen(liste, jetzt + 60, gemeldet, 15, ["USD"]), [])  # nicht doppelt


class TestZentraleServer(unittest.TestCase):
    """Startet den echten Webserver der Zentrale (ohne Mikrofon und ohne Internet)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = mock.patch.object(einstellungen, "DATEN_ORDNER", Path(cls.tmp.name))
        cls.p.start()
        kalender = termine.Terminkalender(Path(cls.tmp.name) / "t.json")
        cls.kasten = werkzeuge.Werkzeugkasten(kalender)
        cls.kasten.melden = lambda text: None
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), zentrale.baue_handler(kalender, cls.kasten))
        cls.port = cls.server.server_address[1]
        cls.port_patch = mock.patch.object(einstellungen, "OBERFLAECHE_PORT", cls.port)
        cls.port_patch.start()
        cls.server.RequestHandlerClass = zentrale.baue_handler(kalender, cls.kasten)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.port_patch.stop()
        cls.p.stop()
        cls.tmp.cleanup()

    def get(self, pfad):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{pfad}", timeout=10) as a:
            return a.read()

    def post(self, pfad, daten, kopf=True):
        anfrage = urllib.request.Request(f"http://127.0.0.1:{self.port}{pfad}", data=json.dumps(daten).encode(),
                                         headers={"Content-Type": "application/json", **({"X-Jarvis": "1"} if kopf else {})})
        with urllib.request.urlopen(anfrage, timeout=10) as a:
            return json.loads(a.read())

    def test_seite_und_einstellungen(self):
        self.assertIn(b"Jarvis Trading-Zentrale", self.get("/"))
        e = json.loads(self.get("/api/einstellungen"))
        self.assertIn("XAUUSD", e["alle_tradingview"])
        self.assertEqual(e["alle_tradingview"]["GOLD"], "OANDA:XAUUSD")

    def test_alarm_und_tagebuch_ueber_die_oberflaeche(self):
        with mock.patch("trading.alarme.waechter_starten"):
            self.assertIn("alarm", self.post("/api/alarm", {"symbol": "XAUUSD", "art": "preis_ueber", "wert": "4200"}))
            alarme = json.loads(self.get("/api/alarme"))["alarme"]
            self.assertTrue(any("Preis über 4200" in a["text"] for a in alarme))
        self.post("/api/tagebuch", {"symbol": "GOLD", "richtung": "LONG", "einstieg": "100", "stop": "99", "ausstieg": "103"})
        tb = json.loads(self.get("/api/tagebuch"))
        self.assertEqual(tb["eintraege"][0]["r"], 3.0)

    def test_positionsrechner(self):
        with mock.patch.object(marktdaten.mt, "kontrakt_info", side_effect=marktdaten.mt.MT5Fehler("aus")):
            d = json.loads(self.get("/api/positionsgroesse?symbol=XAUUSD&einstieg=2400&stop=2398&risiko=0.5"))
        self.assertEqual(d["lots"], 0.25)

    def test_schutz_gegen_fremde_seiten(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.post("/api/frage", {"text": "lösch alles"}, kopf=False)

    def test_chart_befehl_im_zustand(self):
        zentrale.zustand.chart("DAX", "H1")
        z = json.loads(self.get("/api/zustand"))
        self.assertEqual((z["chart_befehl"]["symbol"], z["chart_befehl"]["zeitrahmen"]), ("DAX", "H1"))


class TestSync(unittest.TestCase):
    def ordner_mit(self, dateien, versionen):
        tmp = tempfile.TemporaryDirectory()
        o = Path(tmp.name)
        for name, inhalt in dateien.items():
            (o / name).parent.mkdir(parents=True, exist_ok=True)
            (o / name).write_text(inhalt, encoding="utf-8")
        (o / "versionen.json").write_text(json.dumps(versionen), encoding="utf-8")
        return tmp, o

    def test_findet_nur_eigene_aenderungen_und_keine_geheimnisse(self):
        original = "print('original')"
        tmp, o = self.ordner_mit({
            "gehirn.py": original,                                   # unverändert -> nicht melden
            "oberflaeche.py": "print('von Jarvis umgebaut')",         # geändert
            "plugins/btc.py": "WERKZEUG = {}\ndef ausfuehren(): return 1",  # neu
            ".env": "ANTHROPIC_API_KEY=sk-ant-geheim1234567890",     # nie
            "daten/tagebuch.json": "[]",                              # nie
            "plugins/boese.py": "token = 'ghp_abcdefghijklmnopqrstuvwxyz123'",  # Geheimnis -> übersprungen
        }, {"gehirn.py": [hashlib.sha256(original.encode()).hexdigest()], "oberflaeche.py": ["alt"]})
        with tmp:
            gefunden, uebersprungen = sync.lokale_aenderungen(o)
        self.assertEqual({(d["pfad"], d["status"]) for d in gefunden},
                         {("oberflaeche.py", "geändert"), ("plugins/btc.py", "neu")})
        self.assertEqual([p for p, _ in uebersprungen], ["plugins/boese.py"])

    def test_hochladen_als_ein_commit(self):
        aufrufe = []

        def api(methode, pfad, daten=None, token=None):
            aufrufe.append((methode, pfad, daten))
            if pfad == "git/ref/heads/jarvis-pc":
                return None                               # Zweig gibt es noch nicht
            if pfad.startswith("git/ref/heads/"):
                return {"object": {"sha": "basis"}}
            if pfad == "git/commits/basis":
                return {"tree": {"sha": "baum"}}
            if pfad.startswith("git/trees/baum"):
                return {"tree": [{"path": "jarvis-pc/plugins/alt.py", "type": "blob"}]}
            if pfad == "git/blobs":
                return {"sha": "blob" + str(len(aufrufe))}
            if pfad == "git/trees":
                return {"sha": "neuerbaum"}
            if pfad == "git/commits":
                return {"sha": "abc1234567"}
            return {}

        with mock.patch.object(sync, "_api", side_effect=api):
            r = sync.hochladen("Neues BTC-Werkzeug", dateien=[{"pfad": "plugins/btc.py", "status": "neu", "inhalt": b"x"}],
                               uebersprungen=[])
        self.assertEqual(r["commit"], "abc1234")
        baum = next(d for m, p, d in aufrufe if p == "git/trees")
        pfade = {e["path"]: e["sha"] for e in baum["tree"]}
        self.assertIn("jarvis-pc/plugins/btc.py", pfade)
        self.assertIn("jarvis-pc/BERICHT.md", pfade)
        self.assertIsNone(pfade["jarvis-pc/plugins/alt.py"])           # gelöschtes Plugin wird entfernt
        self.assertIn(("POST", "git/refs"), [(m, p) for m, p, _ in aufrufe])  # Zweig wird angelegt

    def test_neuigkeiten_und_update(self):
        text = "# Titel\n\n## 2026-11-06 · Neu\nMehr Power.\n\n## 2026-11-05 · Alt\nAltes.\n"
        e = sync.neuigkeiten_auswerten(text)
        self.assertEqual([x["kopf"] for x in e], ["2026-11-06 · Neu", "2026-11-05 · Alt"])
        tmp, o = self.ordner_mit({"NEUIGKEITEN.md": "## 2026-11-05 · Alt\nAltes.\n"}, {})
        with tmp, mock.patch.object(sync, "neuigkeiten_github", return_value=e):
            neu = sync.update_pruefen(o)
            grund = sync.fuer_grundanweisung(ordner=o)
        self.assertEqual([x["kopf"] for x in neu], ["2026-11-06 · Neu"])
        self.assertIn("2026-11-05 · Alt", grund)

    def test_neuigkeiten_datei_im_projekt_ist_gueltig(self):
        eintraege = sync.neuigkeiten_lokal()
        self.assertTrue(eintraege)
        datum = eintraege[0]["kopf"].split("·")[0].strip()
        datetime.strptime(datum, "%Y-%m-%d")

    def test_an_claude_melden_braucht_freigabe(self):
        with tempfile.TemporaryDirectory() as tmp:
            kasten = werkzeuge.Werkzeugkasten(termine.Terminkalender(Path(tmp) / "t.json"),
                                              bestaetigen=lambda *a: False)
            with mock.patch.object(sync, "lokale_aenderungen", return_value=([], [])), \
                 mock.patch.object(sync, "hochladen") as hoch:
                self.assertIn("abgelehnt", kasten.ausfuehren("an_claude_melden", {"nachricht": "x"}))
            hoch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
