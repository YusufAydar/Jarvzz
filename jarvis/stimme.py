"""
Hören und Sprechen.

- Hören:    Mikrofon -> Text, über die kostenlose Google-Spracherkennung
            (Paket "SpeechRecognition", braucht Internet).
- Sprechen: Text -> Stimme, über die eingebaute Windows-Stimme
            (keine Installation nötig, deutsche Stimme ist bei deutschem Windows dabei).
"""

import os
import platform
import subprocess
import threading

import einstellungen

IST_WINDOWS = platform.system() == "Windows"

# Kleines PowerShell-Programm, das den Text mit der Windows-Stimme vorliest.
# Der Text kommt über eine Umgebungsvariable rein – so gibt es keine Probleme mit Sonderzeichen.
POWERSHELL_SPRECHEN = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'de*' } | Select-Object -First 1
if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }
$s.Rate = [int]$env:JARVIS_TEMPO
$s.Speak($env:JARVIS_TEXT)
"""

_sprech_sperre = threading.Lock()  # damit nie zwei Sätze gleichzeitig gesprochen werden


def sprechen(text, nur_text=False):
    """Zeigt den Text an und liest ihn vor."""
    print(f"Jarvis: {text}")
    if nur_text:
        return
    with _sprech_sperre:
        if IST_WINDOWS:
            umgebung = dict(os.environ, JARVIS_TEXT=text, JARVIS_TEMPO=str(einstellungen.SPRECHTEMPO))
            subprocess.run(["powershell", "-NoProfile", "-Command", POWERSHELL_SPRECHEN],
                           env=umgebung, creationflags=0x08000000)  # 0x08000000 = kein schwarzes Fenster
        else:
            try:
                import pyttsx3  # Ersatz für Mac/Linux, falls installiert
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass  # ohne Stimme geht es auch – der Text steht ja auf dem Bildschirm


class Ohr:
    """Hört über das Mikrofon zu und macht aus Sprache Text."""

    def __init__(self):
        import speech_recognition as sr  # erst hier laden, damit der Text-Modus ohne läuft
        self.sr = sr
        self.erkenner = sr.Recognizer()
        self.erkenner.pause_threshold = 0.8     # so lange Stille = Satz ist zu Ende
        self.mikrofon = sr.Microphone()
        print("Mikrofon wird eingestellt – bitte kurz still sein ...")
        with self.mikrofon as quelle:
            self.erkenner.adjust_for_ambient_noise(quelle, duration=1.5)

    def hoeren(self, warten_sekunden=None, max_satz_sekunden=15):
        """
        Wartet auf einen gesprochenen Satz und gibt ihn als Text zurück.
        Gibt None zurück, wenn nichts (Verständliches) gesagt wurde.
        """
        try:
            with self.mikrofon as quelle:
                audio = self.erkenner.listen(quelle, timeout=warten_sekunden,
                                             phrase_time_limit=max_satz_sekunden)
            # show_all=True: Google liefert alle Vorschläge statt nur des ersten
            ergebnis = self.erkenner.recognize_google(audio, language=einstellungen.SPRACHE,
                                                      show_all=True)
            return bester_vorschlag(ergebnis)
        except self.sr.WaitTimeoutError:
            return None
        except self.sr.UnknownValueError:
            return None  # Geräusch, aber keine Worte erkannt
        except self.sr.RequestError as fehler:
            print(f"[Spracherkennung nicht erreichbar: {fehler}]")
            return None


def bester_vorschlag(ergebnis):
    """
    Google gibt mehrere Vorschläge zurück, z. B. "Service wie spät ist es" und
    "Jarvis wie spät ist es". Wir nehmen den ersten, der das Wake-Wort enthält,
    sonst einfach den wahrscheinlichsten.
    """
    if not ergebnis or not isinstance(ergebnis, dict):
        return None
    vorschlaege = [v.get("transcript", "") for v in ergebnis.get("alternative", []) if v.get("transcript")]
    if not vorschlaege:
        return None
    for v in vorschlaege:
        if wake_wort_entfernen(v)[0]:
            return v
    return vorschlaege[0]


def wake_wort_entfernen(text):
    """
    Prüft, ob "Jarvis" im Satz vorkommt.
    Gibt (True, rest) zurück – rest ist der Befehl nach dem Wort "Jarvis".
    Beispiel: "Hey Jarvis, wie spät ist es?" -> (True, "wie spät ist es?")
    """
    klein = text.lower()
    for variante in einstellungen.WAKE_WORT_VARIANTEN:
        stelle = klein.find(variante)
        if stelle != -1:
            rest = text[stelle + len(variante):].lstrip(" ,.!?:;-")
            # Falls der Befehl VOR "Jarvis" stand ("Wie spät ist es, Jarvis?")
            if not rest:
                rest = text[:stelle].strip(" ,.!?:;-")
                if rest.lower() in ("hey", "hallo", "hi", "okay", "ok", "he"):
                    rest = ""
            return True, rest
    return False, text
