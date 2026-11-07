"""
Jarvis per Telegram: Meldungen aufs Handy und Fragen/Befehle vom Handy.

Einrichten (einmalig):
  1. In Telegram den Kontakt @BotFather öffnen, /newbot schreiben, Namen vergeben.
     Er schickt einen Schlüssel (Token) – der kommt in jarvis/.env:   TELEGRAM_TOKEN=123456:ABC...
  2. Jarvis neu starten und deinem Bot in Telegram „/start“ schreiben.
     Der Bot antwortet mit deiner Chat-ID – die kommt ebenfalls in jarvis/.env:   TELEGRAM_CHAT_ID=123456789
  3. Jarvis neu starten. Fertig.

Sicherheit:
  - Jarvis antwortet NUR deiner Chat-ID. Nachrichten von anderen werden ignoriert.
  - Riskante Aktionen (Befehle am PC, neue Werkzeuge, Hochladen …) brauchen weiterhin die Freigabe AM PC.
  - Der Token steht nur in .env (wird nie hochgeladen).
"""

import json
import threading
import time
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{methode}"

HILFE = ("Ich bin Jarvis. Schreib mir einfach eine Frage, z. B. „Wie steht Gold?“ oder „Welche News kommen heute?“.\n"
         "Kurzbefehle:\n"
         "/status – Roboter, Paper-Konto, offene Trades\n"
         "/bericht – Trading-Bericht von heute\n"
         "/pause – Roboter pausieren (keine neuen Trades)\n"
         "/weiter – Roboter fortsetzen (nur nach einer Pause, nicht nach einer Drawdown-Sperre)\n"
         "/hilfe – diese Übersicht")


class TelegramBot:
    def __init__(self, token, chat_id=None, fragen=None, trader=None, netz=None):
        """
        fragen: Funktion(text) -> Antwort von Jarvis (Claude)
        trader: die TradingEngine (oder None)
        netz:   nur für Tests – Funktion(methode, daten) -> Antwort-dict
        """
        self.token = token
        self.chat_id = str(chat_id).strip() if chat_id else None
        self.fragen = fragen
        self.trader = trader
        self._netz = netz or self._anfrage
        self.offset = 0

    # ---------- Senden ----------

    def _anfrage(self, methode, daten):
        timeout = 70 if methode == "getUpdates" else 20  # getUpdates wartet bis zu 50 s auf neue Nachrichten
        url = API.format(token=self.token, methode=methode)
        body = urllib.parse.urlencode(daten).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=timeout) as antwort:
            return json.loads(antwort.read().decode("utf-8"))

    def senden(self, text, chat_id=None):
        ziel = chat_id or self.chat_id
        if not ziel or not text:
            return False
        try:
            for teil in range(0, len(text), 4000):  # Telegram erlaubt höchstens 4096 Zeichen pro Nachricht
                self._netz("sendMessage", {"chat_id": ziel, "text": text[teil:teil + 4000]})
            return True
        except Exception as fehler:
            print(f"[Telegram: Senden fehlgeschlagen: {fehler}]")
            return False

    # ---------- Empfangen ----------

    def verarbeiten(self, update):
        """Eine eingehende Nachricht verarbeiten. Gibt die Antwort zurück (oder None, wenn ignoriert)."""
        nachricht = update.get("message") or {}
        text = (nachricht.get("text") or "").strip()
        chat = str((nachricht.get("chat") or {}).get("id", ""))
        if not text or not chat:
            return None
        if not self.chat_id:
            antwort = (f"Hallo! Deine Chat-ID ist {chat}.\nTrag in jarvis/.env diese Zeile ein:\n"
                       f"TELEGRAM_CHAT_ID={chat}\nund starte Jarvis neu. Erst dann höre ich auf dich.")
            self.senden(antwort, chat)
            return antwort
        if chat != self.chat_id:
            print(f"[Telegram: Nachricht von fremder Chat-ID {chat} ignoriert]")
            return None
        antwort = self.befehl(text)
        self.senden(antwort)
        return antwort

    def befehl(self, text):
        wort = text.split()[0].lower().split("@")[0]
        t = self.trader
        if wort in ("/start", "/hilfe", "/help"):
            return HILFE
        if wort in ("/status", "/bericht", "/pause", "/weiter") and t is None:
            return "Der Trading-Roboter läuft gerade nicht (nur in der Trading-Zentrale)."
        if wort == "/status":
            return status_text(t.status_daten())
        if wort == "/bericht":
            from trader import bericht, risiko
            return bericht.tagesbericht(t, risiko.tagesbeginn(time.time()))
        if wort == "/pause":
            return t.steuern("pause")
        if wort == "/weiter":
            if t.status != "pausiert":
                return (f"Der Roboter ist „{t.status}“. Vom Handy aus kann ich nur eine normale Pause aufheben – "
                        "nach Not-Aus oder Drawdown-Sperre bitte am PC prüfen.")
            return t.steuern("fortsetzen")
        if wort.startswith("/"):
            return "Den Befehl kenne ich nicht.\n\n" + HILFE
        if self.fragen is None:
            return "Fragen kann ich gerade nicht beantworten."
        return self.fragen(text)

    def lauschen(self):
        """Dauerschleife: holt neue Nachrichten (Long-Polling) und beantwortet sie."""
        fehler_in_folge = 0
        while True:
            try:
                antwort = self._netz("getUpdates", {"offset": self.offset, "timeout": 50})
                for update in antwort.get("result", []):
                    self.offset = update["update_id"] + 1
                    try:
                        self.verarbeiten(update)
                    except Exception as fehler:
                        self.senden(f"Da ist etwas schiefgegangen: {fehler}")
                fehler_in_folge = 0
            except Exception as fehler:
                fehler_in_folge += 1
                if fehler_in_folge in (1, 10):
                    print(f"[Telegram nicht erreichbar: {fehler}]")
                time.sleep(min(60, 5 * fehler_in_folge))

    def starten(self):
        threading.Thread(target=self.lauschen, daemon=True).start()


def status_text(d):
    s = d["statistik"]
    zeilen = [f"Roboter: {d['status']}" + (f" ({d['grund']})" if d.get("grund") else "") + f" – {d['modus']}, Stufe {d['stufe']}",
              f"Paper-Konto: {d['equity']:.2f} $ (Start {d['start']:.0f} $), heute {d['heute']:+.2f} $",
              f"Roboter-Trades gesamt: {s['trades']}" + (f", Win-Rate {s['win_rate'] * 100:.0f} %, Netto {s['netto']:+.2f} $"
                                                        if s["trades"] else "")]
    if d.get("statistik_manuell", {}).get("trades"):
        m = d["statistik_manuell"]
        zeilen.append(f"Manuelle Trades: {m['trades']}, Netto {m['netto']:+.2f} $")
    if d["offene"]:
        zeilen.append("Offen:")
        for p in d["offene"]:
            zeilen.append(f"  #{p['id']} {p['symbol']} {p['richtung']} ab {p['einstieg']}, Stop {p['stop']}, "
                          f"Ziel {p['ziel']}, aktuell {p['stand']:+.2f} $")
    else:
        zeilen.append("Keine offenen Positionen.")
    zeilen.append("Handelszeit: " + ("ja" if d["in_handelszeit"] else "nein") + f" ({d['handelszeit'][0]}–{d['handelszeit'][1]})")
    return "\n".join(zeilen)
