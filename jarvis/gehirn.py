"""
Das "Gehirn" von Jarvis: die Verbindung zu Claude.

Ablauf bei jeder Frage:
  1. Deine Frage (plus aktuelle Uhrzeit) geht an Claude.
  2. Claude antwortet entweder direkt – oder sagt "ich brauche Werkzeug X".
  3. Dann führen wir das Werkzeug aus, schicken das Ergebnis zurück, und Claude antwortet.
  4. Das wiederholt sich, bis Claude fertig ist.
"""

import time

import anthropic

import einstellungen
import werkzeuge

SYSTEM_ANWEISUNG = """Du bist Jarvis, der persönliche Sprachassistent von Yusuf und Marko.
Du läufst auf ihrem Windows-PC. Alles, was du schreibst, wird laut vorgelesen.

So antwortest du:
- Auf Deutsch, freundlich, mit einer Prise trockenem Humor – wie ein souveräner Butler.
- Kurz: meistens ein bis drei Sätze. Längere Antworten nur, wenn ausdrücklich gewünscht.
- Keine Aufzählungszeichen, keine Tabellen, kein Markdown, keine Emojis, keine Links –
  das kann man nicht vorlesen. Zahlen so schreiben, wie man sie spricht.

Werkzeuge:
- Nutze deine Werkzeuge, wenn eine Aufgabe sie braucht (Termine, Programme, Lautstärke,
  Dateien, Hyperliquid-Bericht, Websuche). Sag danach kurz, was du getan hast.
- Jede Nachricht beginnt mit der aktuellen Uhrzeit. Rechne damit relative Zeitangaben um.
- Bei Fragen zu Hyperliquid oder Top-Tradern: hole den Bericht und fasse das Wichtigste in
  zwei bis vier gesprochenen Sätzen zusammen. Weise bei Kaufentscheidungen kurz darauf hin,
  dass das keine Anlageberatung ist.
- Handle selbstständig: Wer sagt "öffne", "spiel", "zeig mir", meint, dass du es sofort tust.
  Videos und Musikvideos spielst du mit youtube_abspielen ab, Programme öffnest du mit
  programm_oeffnen, für Google-Suchen öffnest du https://www.google.com/search?q=... mit
  webseite_oeffnen. Ergänze bei Bedarf sinnvolle Suchbegriffe (z. B. den Künstlernamen).
- Wenn du dir bei einer Aktion wirklich unsicher bist, frag kurz nach, statt zu raten.
"""


class Gehirn:
    def __init__(self, werkzeugkasten, client=None, beobachter=None):
        # Der Client liest den API-Schlüssel automatisch aus ANTHROPIC_API_KEY
        self.client = client or anthropic.Anthropic()
        # Optional: wird bei jedem benutzten Werkzeug aufgerufen (für die Oberfläche)
        self.beobachter = beobachter or (lambda name, eingaben: None)
        self.werkzeugkasten = werkzeugkasten
        self.werkzeuge = werkzeuge.alle_werkzeuge()
        self.verlauf = []          # bisheriges Gespräch
        self.letzte_frage = 0.0

    def neues_gespraech(self):
        self.verlauf = []

    def frage(self, text):
        """Schickt eine Frage an Claude und gibt die Antwort als Text zurück."""
        # Nach längerer Pause neues Gespräch beginnen (spart Kosten)
        if time.time() - self.letzte_frage > einstellungen.GESPRAECH_NEU_NACH_MINUTEN * 60:
            self.neues_gespraech()
        self.letzte_frage = time.time()

        self.verlauf.append({
            "role": "user",
            "content": f"[Aktuelle Zeit: {werkzeuge.aktuelle_zeit_text()}]\n{text}",
        })

        try:
            return self._denken()
        except anthropic.AuthenticationError:
            return "Mein API-Schlüssel funktioniert nicht. Bitte prüfe die Datei punkt e n v."
        except anthropic.PermissionDeniedError:
            return "Mein API-Schlüssel hat keine Berechtigung dafür."
        except anthropic.RateLimitError:
            return "Ich bekomme gerade zu viele Anfragen. Versuch es gleich noch einmal."
        except anthropic.APIConnectionError:
            return "Ich erreiche das Internet gerade nicht."
        except anthropic.APIStatusError as fehler:
            print(f"[Fehler von Claude] {fehler.status_code}: {fehler.message}")
            # Bei einem Fehler im Gesprächsverlauf lieber neu anfangen
            self.neues_gespraech()
            return "Da ist etwas schiefgelaufen. Ich habe das Gespräch neu gestartet."

    def _denken(self):
        for _ in range(10):  # höchstens 10 Runden mit Werkzeugen, dann Schluss
            antwort = self.client.beta.messages.create(
                model=einstellungen.MODELL,
                max_tokens=16000,
                system=SYSTEM_ANWEISUNG,
                tools=self.werkzeuge,
                messages=self.verlauf,
                output_config={"effort": einstellungen.DENKTIEFE},
                cache_control={"type": "ephemeral"},     # spart Kosten bei langen Gesprächen
                # Falls Claude eine Anfrage ablehnt, übernimmt automatisch ein anderes Modell
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )

            if antwort.stop_reason == "refusal":
                # Abgelehntes Gespräch nicht weiterführen
                self.neues_gespraech()
                return "Dabei kann ich leider nicht helfen."

            # Die komplette Antwort (inkl. Denk-Blöcken) unverändert im Verlauf speichern
            self.verlauf.append({"role": "assistant", "content": antwort.content})

            if antwort.stop_reason == "pause_turn":
                continue  # Websuche braucht noch eine Runde

            if antwort.stop_reason != "tool_use":
                return _text_aus(antwort) or "Erledigt."

            # Alle gewünschten Werkzeuge ausführen und die Ergebnisse zurückschicken
            ergebnisse = []
            for block in antwort.content:
                if block.type != "tool_use":
                    continue
                print(f"  [Werkzeug] {block.name} {block.input}")
                self.beobachter(block.name, dict(block.input))
                try:
                    inhalt = self.werkzeugkasten.ausfuehren(block.name, dict(block.input))
                    ergebnisse.append({"type": "tool_result", "tool_use_id": block.id,
                                       "content": inhalt})
                except Exception as fehler:
                    ergebnisse.append({"type": "tool_result", "tool_use_id": block.id,
                                       "content": f"Fehler: {fehler}", "is_error": True})
            self.verlauf.append({"role": "user", "content": ergebnisse})

        return "Das war mir zu kompliziert. Kannst du es anders formulieren?"


def _text_aus(antwort):
    return " ".join(b.text for b in antwort.content if b.type == "text").strip()
