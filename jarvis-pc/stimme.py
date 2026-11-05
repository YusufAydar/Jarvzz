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
_ohr = None  # wird von Ohr() gesetzt, damit wir beim Sprechen aufs Mikrofon hören können

# Unterbrechen: Wenn jemand ins Mikrofon spricht, während Jarvis redet, hört Jarvis auf.
UNTERBRECHEN = getattr(einstellungen, "UNTERBRECHEN", True)
UNTERBRECHEN_FAKTOR = getattr(einstellungen, "UNTERBRECHEN_FAKTOR", 3.0)       # wie viel lauter als normal
UNTERBRECHEN_MIN_SEKUNDEN = getattr(einstellungen, "UNTERBRECHEN_MIN_SEKUNDEN", 0.35)  # so lange am Stück


def _lautstaerke(daten):
    """RMS-Lautstärke eines 16-Bit-Audioblocks (ohne audioop, läuft auch auf neuem Python)."""
    import array
    werte = array.array("h", daten)
    if not werte:
        return 0
    return (sum(w * w for w in werte) / len(werte)) ** 0.5


def _abspielen_mit_unterbrechung(prozess):
    """Wartet, bis der Sprech-Prozess fertig ist – bricht ihn ab, sobald jemand spricht."""
    if not (UNTERBRECHEN and _ohr is not None):
        prozess.wait()
        return False
    stream = None
    try:
        import pyaudio
        pa = _ohr.mikrofon.pyaudio_module.PyAudio() if hasattr(_ohr.mikrofon, "pyaudio_module") else pyaudio.PyAudio()
        rate, block = 16000, 1024
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True,
                         frames_per_buffer=block, input_device_index=_ohr.mikrofon.device_index)
        schwelle = max(_ohr.erkenner.energy_threshold * UNTERBRECHEN_FAKTOR, 600)
        noetig = max(1, int(UNTERBRECHEN_MIN_SEKUNDEN * rate / block))
        laut_in_folge, bloecke = 0, 0
        while prozess.poll() is None:
            daten = stream.read(block, exception_on_overflow=False)
            bloecke += 1
            if bloecke < 8:  # die ersten ~0,5 s ignorieren (Anlaufen der Stimme)
                continue
            laut_in_folge = laut_in_folge + 1 if _lautstaerke(daten) > schwelle else 0
            if laut_in_folge >= noetig:
                prozess.kill()
                print("[Unterbrochen – ich höre zu]")
                return True
        return False
    except Exception as fehler:
        print(f"[Unterbrechen nicht möglich: {fehler}]")
        prozess.wait()
        return False
    finally:
        try:
            if stream is not None:
                stream.stop_stream()
                stream.close()
                pa.terminate()
        except Exception:
            pass


def sprechen(text, nur_text=False):
    """Zeigt den Text an und liest ihn vor. Gibt True zurück, wenn unterbrochen wurde."""
    print(f"Jarvis: {text}")
    if nur_text:
        return False
    with _sprech_sperre:
        if IST_WINDOWS:
            umgebung = dict(os.environ, JARVIS_TEXT=text, JARVIS_TEMPO=str(einstellungen.SPRECHTEMPO))
            prozess = subprocess.Popen(["powershell", "-NoProfile", "-Command", POWERSHELL_SPRECHEN],
                                       env=umgebung, creationflags=0x08000000)  # kein schwarzes Fenster
            return _abspielen_mit_unterbrechung(prozess)
        else:
            try:
                import pyttsx3  # Ersatz für Mac/Linux, falls installiert
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass  # ohne Stimme geht es auch – der Text steht ja auf dem Bildschirm
            return False


class Ohr:
    """Hört über das Mikrofon zu und macht aus Sprache Text."""

    def __init__(self):
        global _ohr
        import speech_recognition as sr  # erst hier laden, damit der Text-Modus ohne läuft
        self.sr = sr
        self.erkenner = sr.Recognizer()
        self.erkenner.pause_threshold = 0.8     # so lange Stille = Satz ist zu Ende
        self.mikrofon = sr.Microphone()
        print("Mikrofon wird eingestellt – bitte kurz still sein ...")
        with self.mikrofon as quelle:
            self.erkenner.adjust_for_ambient_noise(quelle, duration=1.5)
        _ohr = self

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
