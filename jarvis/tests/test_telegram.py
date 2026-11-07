"""Tests für den Telegram-Bot – ohne Internet (Netz wird nachgebaut)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import telegram_bot  # noqa: E402


class FalscherTrader:
    def __init__(self, status="aktiv"):
        self.status = status
        self.aufrufe = []

    def steuern(self, aktion):
        self.aufrufe.append(aktion)
        return f"ok {aktion}"

    def status_daten(self):
        return {"status": self.status, "grund": "", "modus": "PAPER", "stufe": 1, "equity": 10050.0, "start": 10000,
                "heute": 50.0, "statistik": {"trades": 2, "win_rate": 0.5, "netto": 50.0},
                "statistik_manuell": {"trades": 0}, "offene": [], "in_handelszeit": True,
                "handelszeit": ("09:00", "21:00")}


def nachricht(text, chat=42, update_id=1):
    return {"update_id": update_id, "message": {"text": text, "chat": {"id": chat}}}


class TestTelegram(unittest.TestCase):
    def bot(self, chat_id="42", trader=None, fragen=None):
        self.gesendet = []
        netz = lambda methode, daten: self.gesendet.append((methode, daten)) or {"ok": True, "result": []}
        return telegram_bot.TelegramBot("TOKEN", chat_id, fragen=fragen, trader=trader, netz=netz)

    def test_ohne_chat_id_nennt_er_nur_die_id(self):
        b = self.bot(chat_id=None, fragen=lambda t: "geheim")
        antwort = b.verarbeiten(nachricht("/start", chat=777))
        self.assertIn("TELEGRAM_CHAT_ID=777", antwort)
        self.assertNotIn("geheim", antwort)

    def test_fremde_werden_ignoriert(self):
        b = self.bot(fragen=lambda t: "Antwort")
        self.assertIsNone(b.verarbeiten(nachricht("Wie steht Gold?", chat=999)))
        self.assertEqual(self.gesendet, [])

    def test_frage_geht_an_jarvis(self):
        b = self.bot(fragen=lambda t: f"Jarvis sagt: {t}")
        self.assertEqual(b.verarbeiten(nachricht("Wie steht Gold?")), "Jarvis sagt: Wie steht Gold?")
        self.assertEqual(self.gesendet[0][1]["chat_id"], "42")

    def test_status_und_pause(self):
        t = FalscherTrader()
        b = self.bot(trader=t)
        self.assertIn("Paper-Konto: 10050.00", b.verarbeiten(nachricht("/status")))
        b.verarbeiten(nachricht("/pause"))
        self.assertEqual(t.aufrufe, ["pause"])

    def test_weiter_nur_nach_normaler_pause(self):
        gesperrt = FalscherTrader("gesperrt")
        self.assertIn("am PC", self.bot(trader=gesperrt).befehl("/weiter"))
        self.assertEqual(gesperrt.aufrufe, [])
        pausiert = FalscherTrader("pausiert")
        self.bot(trader=pausiert).befehl("/weiter")
        self.assertEqual(pausiert.aufrufe, ["fortsetzen"])

    def test_lange_nachrichten_werden_geteilt(self):
        b = self.bot()
        b.senden("x" * 9000)
        self.assertEqual(len(self.gesendet), 3)

    def test_unbekannter_befehl(self):
        self.assertIn("kenne ich nicht", self.bot().befehl("/zauber"))


if __name__ == "__main__":
    unittest.main()
