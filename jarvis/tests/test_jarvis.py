"""
Tests für Jarvis – laufen ohne Mikrofon, ohne Internet und ohne API-Schlüssel.
Claude wird hier durch einen "Schauspieler" (FakeClient) ersetzt, der vorher
festgelegte Antworten gibt. So prüfen wir, ob unser Ablauf stimmt.

Starten (im Ordner jarvis):
    python -m unittest discover tests -v
"""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import einstellungen  # noqa: E402
import gehirn  # noqa: E402
import stimme  # noqa: E402
import termine  # noqa: E402
import werkzeuge  # noqa: E402


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(name, eingaben, block_id="tool_1"):
    return SimpleNamespace(type="tool_use", name=name, input=eingaben, id=block_id)


def antwort(stop_reason, *bloecke):
    return SimpleNamespace(stop_reason=stop_reason, content=list(bloecke))


class FakeClient:
    """Tut so, als wäre er Claude, und merkt sich alle Anfragen."""

    def __init__(self, antworten):
        self.antworten = list(antworten)
        self.anfragen = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **anfrage):
        # Kopie des Verlaufs merken (die Liste wird später weiter verändert)
        anfrage = dict(anfrage, messages=list(anfrage["messages"]))
        self.anfragen.append(anfrage)
        return self.antworten.pop(0)


class TestTermine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kalender = termine.Terminkalender(Path(self.tmp.name) / "termine.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_erinnerung_wird_zur_richtigen_zeit_gemeldet(self):
        self.kalender.hinzufuegen("erinnerung", "Mama anrufen", "2026-11-05T18:00")
        self.assertEqual(self.kalender.faellige(datetime(2026, 11, 5, 17, 59)), [])
        faellig = self.kalender.faellige(datetime(2026, 11, 5, 18, 0))
        self.assertEqual(faellig[0]["text"], "Mama anrufen")
        # Kein zweites Mal melden
        self.assertEqual(self.kalender.faellige(datetime(2026, 11, 5, 18, 5)), [])

    def test_termin_mit_vorwarnung(self):
        e = self.kalender.hinzufuegen("termin", "Zahnarzt", "2026-11-06T10:00", minuten_vorher=30)
        self.assertEqual(e["melden_um"], "2026-11-06T09:30")
        self.assertIn("Um 10:00 Uhr", termine.meldung_fuer(e))

    def test_bleibt_nach_neustart_gespeichert(self):
        self.kalender.hinzufuegen("termin", "Training", "2026-11-07T19:00")
        neu_geladen = termine.Terminkalender(self.kalender.datei)
        self.assertEqual(neu_geladen.auflisten()[0]["text"], "Training")

    def test_loeschen_und_tagesueberblick(self):
        e = self.kalender.hinzufuegen("termin", "Meeting", "2026-11-05T15:00")
        text = termine.tagesueberblick(self.kalender, datetime(2026, 11, 5, 8, 0))
        self.assertIn("Guten Morgen", text)
        self.assertIn("15:00 Uhr Meeting", text)
        self.assertTrue(self.kalender.loeschen(e["id"]))
        self.assertEqual(self.kalender.auflisten(), [])


class TestGehirn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kalender = termine.Terminkalender(Path(self.tmp.name) / "termine.json")
        self.kasten = werkzeuge.Werkzeugkasten(self.kalender)

    def tearDown(self):
        self.tmp.cleanup()

    def test_einfache_antwort(self):
        client = FakeClient([antwort("end_turn", text_block("Es ist 12 Uhr."))])
        g = gehirn.Gehirn(self.kasten, client=client)
        self.assertEqual(g.frage("Wie spät ist es?"), "Es ist 12 Uhr.")
        anfrage = client.anfragen[0]
        self.assertEqual(anfrage["model"], "claude-opus-5-5")
        self.assertEqual(anfrage["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", anfrage["betas"])
        self.assertIn("[Aktuelle Zeit:", anfrage["messages"][0]["content"])

    def test_werkzeug_wird_benutzt(self):
        client = FakeClient([
            antwort("tool_use", tool_block("termin_eintragen", {
                "art": "erinnerung", "text": "Pizza holen", "zeitpunkt": "2026-11-05T19:30"})),
            antwort("end_turn", text_block("Ich erinnere dich um halb acht.")),
        ])
        benutzt = []
        g = gehirn.Gehirn(self.kasten, client=client, beobachter=lambda n, e: benutzt.append(n))
        self.assertEqual(g.frage("Erinnere mich um 19:30 an die Pizza"),
                         "Ich erinnere dich um halb acht.")
        self.assertEqual(benutzt, ["termin_eintragen"])  # die Oberfläche wird informiert
        self.assertEqual(self.kalender.auflisten()[0]["text"], "Pizza holen")
        # Zweite Anfrage enthält das Werkzeug-Ergebnis
        ergebnis = client.anfragen[1]["messages"][-1]["content"][0]
        self.assertEqual(ergebnis["type"], "tool_result")
        self.assertEqual(ergebnis["tool_use_id"], "tool_1")
        self.assertIn("Gespeichert", ergebnis["content"])

    def test_werkzeug_fehler_wird_an_claude_gemeldet(self):
        client = FakeClient([
            antwort("tool_use", tool_block("termin_eintragen", {
                "art": "termin", "text": "X", "zeitpunkt": "morgen irgendwann"})),
            antwort("end_turn", text_block("Welche Uhrzeit genau?")),
        ])
        g = gehirn.Gehirn(self.kasten, client=client)
        self.assertEqual(g.frage("Trag einen Termin ein"), "Welche Uhrzeit genau?")
        ergebnis = client.anfragen[1]["messages"][-1]["content"][0]
        self.assertTrue(ergebnis["is_error"])

    def test_gespraech_wird_fortgesetzt(self):
        client = FakeClient([antwort("end_turn", text_block("Hallo Yusuf.")),
                             antwort("end_turn", text_block("Du heißt Yusuf."))])
        g = gehirn.Gehirn(self.kasten, client=client)
        g.frage("Ich bin Yusuf")
        g.frage("Wie heiße ich?")
        self.assertEqual(len(client.anfragen[1]["messages"]), 3)  # Frage, Antwort, neue Frage

    def test_ablehnung(self):
        client = FakeClient([antwort("refusal")])
        g = gehirn.Gehirn(self.kasten, client=client)
        self.assertEqual(g.frage("..."), "Dabei kann ich leider nicht helfen.")
        self.assertEqual(g.verlauf, [])


class TestWerkzeuge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kasten = werkzeuge.Werkzeugkasten(
            termine.Terminkalender(Path(self.tmp.name) / "termine.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_alle_werkzeuge_haben_eine_funktion(self):
        for w in werkzeuge.WERKZEUG_BESCHREIBUNGEN:
            self.assertTrue(hasattr(self.kasten, f"_{w['name']}"), w["name"])

    def test_app_im_startmenue_finden(self):
        apps = [{"Name": "Discord", "AppID": "com.squirrel.Discord.Discord"},
                {"Name": "Discord deinstallieren", "AppID": "x"},
                {"Name": "Steam", "AppID": "Valve.Steam"},
                {"Name": "Spotify", "AppID": "SpotifyAB.Spotify"}]
        self.assertEqual(werkzeuge.finde_app("discord", apps)["AppID"], "com.squirrel.Discord.Discord")
        self.assertEqual(werkzeuge.finde_app("Spot", apps)["Name"], "Spotify")
        self.assertIsNone(werkzeuge.finde_app("Fortnite", apps))

    def test_youtube_erstes_video(self):
        html = ('..."videoRenderer":{"videoId":"abcDEF12345","thumbnail":{},'
                '"title":{"runs":[{"text":"Haftbefehl - Chabos wissen wer der Babo ist"}]}...'
                '"videoRenderer":{"videoId":"zzzzzzzzzzz","title":{"runs":[{"text":"Zweites"}]}')
        self.assertEqual(werkzeuge.youtube_erstes_video("haftbefehl", html=html),
                         ("abcDEF12345", "Haftbefehl - Chabos wissen wer der Babo ist"))
        self.assertEqual(werkzeuge.youtube_erstes_video("x", html="nichts"), (None, None))

    def test_youtube_oeffnet_video(self):
        with mock.patch.object(werkzeuge, "youtube_erstes_video", return_value=("abcDEF12345", "Titel")), \
             mock.patch.object(werkzeuge.webbrowser, "open") as geoeffnet:
            text = self.kasten.ausfuehren("youtube_abspielen", {"suche": "haftbefehl"})
        geoeffnet.assert_called_once_with("https://www.youtube.com/watch?v=abcDEF12345")
        self.assertIn("Titel", text)

    def test_hyperliquid_bericht_lokal(self):
        bericht = Path(self.tmp.name) / "aktuell.md"
        bericht.write_text("# Tagesbericht\nBTC: KAUFEN", encoding="utf-8")
        with mock.patch.object(einstellungen, "HYPERLIQUID_BERICHT_LOKAL", bericht):
            text = self.kasten.ausfuehren("hyperliquid_bericht", {})
        self.assertIn("BTC: KAUFEN", text)
        self.assertIn("lokaler Bericht", text)

    def test_datei_suchen_und_oeffnen_nur_in_erlaubten_ordnern(self):
        heim = Path(self.tmp.name)
        (heim / "Documents").mkdir()
        (heim / "Documents" / "Steuer_2026.pdf").write_text("x")
        (heim / "AppData").mkdir()
        (heim / "AppData" / "geheim.txt").write_text("x")
        with mock.patch.object(Path, "home", return_value=heim):
            treffer = self.kasten.ausfuehren("datei_suchen", {"suchbegriff": "steuer"})
            self.assertIn("Steuer_2026.pdf", treffer)
            self.assertIn("Ich öffne nur", self.kasten.ausfuehren(
                "datei_oeffnen", {"pfad": str(heim / "AppData" / "geheim.txt")}))


class TestWakeWort(unittest.TestCase):
    def test_varianten(self):
        self.assertEqual(stimme.wake_wort_entfernen("Hey Jarvis, wie spät ist es?"),
                         (True, "wie spät ist es?"))
        self.assertEqual(stimme.wake_wort_entfernen("Wie spät ist es, Jarvis?"),
                         (True, "Wie spät ist es"))
        self.assertEqual(stimme.wake_wort_entfernen("hey Jarvis"), (True, ""))
        self.assertEqual(stimme.wake_wort_entfernen("Mach mal Musik an")[0], False)
        self.assertEqual(stimme.wake_wort_entfernen("Service mach lauter"), (True, "mach lauter"))

    def test_bester_vorschlag(self):
        ergebnis = {"alternative": [{"transcript": "Paris wie spät ist es"},
                                    {"transcript": "Jarvis wie spät ist es"}]}
        self.assertEqual(stimme.bester_vorschlag(ergebnis), "Jarvis wie spät ist es")
        self.assertEqual(stimme.bester_vorschlag({"alternative": [{"transcript": "Hallo"}]}), "Hallo")
        self.assertIsNone(stimme.bester_vorschlag([]))  # Google liefert [] bei Stille


if __name__ == "__main__":
    unittest.main()
