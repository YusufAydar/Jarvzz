"""Tests für Vollzugriff, selbstgebaute Werkzeuge und den Updater."""

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gehirn  # noqa: E402
import termine  # noqa: E402
import updater  # noqa: E402
import vollzugriff  # noqa: E402
import werkzeuge  # noqa: E402

PLUGIN = '''
WERKZEUG = {
    "name": "verdoppeln",
    "description": "Verdoppelt eine Zahl",
    "input_schema": {"type": "object", "properties": {"zahl": {"type": "number"}}, "required": ["zahl"]},
}

def ausfuehren(zahl):
    return f"Ergebnis: {zahl * 2}"
'''


class TestPlugins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(vollzugriff, "PLUGIN_ORDNER", Path(self.tmp.name) / "plugins")
        self.patch.start()
        self.gefragt = []

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def kasten(self, erlauben):
        def bestaetigen(art, beschreibung, details):
            self.gefragt.append((art, beschreibung, details))
            return erlauben
        return werkzeuge.Werkzeugkasten(termine.Terminkalender(Path(self.tmp.name) / "t.json"), bestaetigen)

    def test_werkzeug_bauen_und_benutzen(self):
        k = self.kasten(erlauben=True)
        text = k.ausfuehren("werkzeug_erstellen", {"name": "verdoppeln", "zweck": "verdoppelt", "python_code": PLUGIN})
        self.assertIn("gespeichert", text)
        self.assertEqual(self.gefragt[0][0], "werkzeug")
        self.assertIn("def ausfuehren", self.gefragt[0][2])          # der Code wurde zum Prüfen gezeigt
        self.assertTrue(k.werkzeuge_geaendert)
        self.assertIn("verdoppeln", [w["name"] for w in k.werkzeug_liste()])
        self.assertEqual(k.ausfuehren("verdoppeln", {"zahl": 21}), "Ergebnis: 42")
        # Nach einem Neustart ist es immer noch da
        self.assertIn("verdoppeln", self.kasten(erlauben=False).plugins)

    def test_ohne_freigabe_wird_nichts_gespeichert(self):
        k = self.kasten(erlauben=False)
        text = k.ausfuehren("werkzeug_erstellen", {"name": "verdoppeln", "zweck": "x", "python_code": PLUGIN})
        self.assertIn("NICHT erlaubt", text)
        self.assertFalse((vollzugriff.PLUGIN_ORDNER / "verdoppeln.py").exists())

    def test_kaputter_code_und_namen_werden_abgelehnt(self):
        k = self.kasten(erlauben=True)
        self.assertIn("Syntaxfehler", k.ausfuehren("werkzeug_erstellen", {"name": "x_y", "zweck": "x", "python_code": "def ("}))
        self.assertIn("fehlt", k.ausfuehren("werkzeug_erstellen", {"name": "x_y", "zweck": "x", "python_code": "a = 1"}))
        self.assertIn("Ungültiger Name", k.ausfuehren("werkzeug_erstellen", {"name": "../böse", "zweck": "x", "python_code": PLUGIN}))
        self.assertIn("eingebautes", k.ausfuehren("werkzeug_erstellen", {"name": "pc_sperren", "zweck": "x", "python_code": PLUGIN}))
        self.assertEqual(self.gefragt, [])  # bei Fehlern wird gar nicht erst gefragt

    def test_gehirn_nimmt_neue_werkzeuge_ab_der_naechsten_frage(self):
        k = self.kasten(erlauben=True)
        antworten = [
            SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(
                type="tool_use", id="t1", name="werkzeug_erstellen",
                input={"name": "verdoppeln", "zweck": "x", "python_code": PLUGIN})]),
            SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Gebaut.")]),
            SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="42")]),
        ]
        anfragen = []
        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(
            create=lambda **a: (anfragen.append(dict(a, messages=list(a["messages"]))), antworten.pop(0))[1])))
        g = gehirn.Gehirn(k, client=client)
        g.frage("Bau dir ein Werkzeug zum Verdoppeln")
        namen_vorher = [w["name"] for w in anfragen[1]["tools"]]
        self.assertNotIn("verdoppeln", namen_vorher)    # innerhalb des Gesprächs bleibt die Liste gleich
        g.frage("Verdopple 21")
        self.assertIn("verdoppeln", [w["name"] for w in anfragen[2]["tools"]])
        self.assertEqual(len(anfragen[2]["messages"]), 1)  # neues Gespräch mit neuer Werkzeugliste


class TestBefehle(unittest.TestCase):
    def test_befehl_braucht_freigabe(self):
        with mock.patch.object(vollzugriff, "IST_WINDOWS", True), \
             mock.patch.object(vollzugriff.subprocess, "run") as ausfuehren:
            text = vollzugriff.befehl_ausfuehren("Remove-Item x", "löscht x", lambda *a: False)
        self.assertIn("NICHT erlaubt", text)
        ausfuehren.assert_not_called()

    def test_befehl_mit_freigabe(self):
        fertig = SimpleNamespace(returncode=0, stdout="Hallo", stderr="")
        with mock.patch.object(vollzugriff, "IST_WINDOWS", True), \
             mock.patch.object(vollzugriff.subprocess, "run", return_value=fertig):
            text = vollzugriff.befehl_ausfuehren("echo Hallo", "sagt Hallo", lambda *a: True)
        self.assertIn("Hallo", text)

    def test_ja_erkennen(self):
        self.assertTrue(vollzugriff.ist_ja("Ja."))
        self.assertTrue(vollzugriff.ist_ja("ja mach"))
        self.assertFalse(vollzugriff.ist_ja("nein"))
        self.assertFalse(vollzugriff.ist_ja("jahr 2026"))
        self.assertFalse(vollzugriff.ist_ja(None))


class TestUpdater(unittest.TestCase):
    def test_persoenliche_dateien_bleiben(self):
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w") as z:
            z.writestr("Jarvzz-main/README.md", "x")
            z.writestr("Jarvzz-main/jarvis/gehirn.py", "NEU")
            z.writestr("Jarvzz-main/jarvis/.env", "FREMDER SCHLÜSSEL")
            z.writestr("Jarvzz-main/jarvis/plugins/fremd.py", "x")
            z.writestr("Jarvzz-main/jarvis/oberflaeche/index.html", "NEU")
        with tempfile.TemporaryDirectory() as tmp:
            ziel = Path(tmp)
            (ziel / ".env").write_text("MEIN SCHLÜSSEL", encoding="utf-8")
            (ziel / "gehirn.py").write_text("ALT")
            anzahl = updater.entpacken(zipfile.ZipFile(puffer), ziel)
            self.assertEqual(anzahl, 2)
            self.assertEqual((ziel / "gehirn.py").read_text(), "NEU")
            self.assertEqual((ziel / "oberflaeche" / "index.html").read_text(), "NEU")
            self.assertEqual((ziel / ".env").read_text(encoding="utf-8"), "MEIN SCHLÜSSEL")
            self.assertFalse((ziel / "plugins" / "fremd.py").exists())


if __name__ == "__main__":
    unittest.main()
