"""
Vollzugriff: Jarvis darf beliebige PowerShell-Befehle ausführen und sich selbst
neue Werkzeuge (Plugins) bauen.

Sicherung: Vor JEDER dieser Aktionen wird dir genau gezeigt, was passieren soll,
und du musst bestätigen (Klick in der Oberfläche oder "Ja" sagen/tippen).
Das lässt sich in einstellungen.py abschalten (BEFEHLE_OHNE_NACHFRAGE) – nicht empfohlen.

Plugins liegen im Ordner jarvis/plugins/. Jedes Plugin ist eine Python-Datei mit:
    WERKZEUG = {"name": "...", "description": "...", "input_schema": {...}}
    def ausfuehren(**eingaben) -> str
Ein Plugin löschst du, indem du seine Datei aus dem Ordner löschst.
"""

import ast
import importlib.util
import keyword
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

import einstellungen

PLUGIN_ORDNER = Path(__file__).resolve().parent / "plugins"
IST_WINDOWS = platform.system() == "Windows"

BESCHREIBUNGEN = [
    {
        "name": "befehl_ausfuehren",
        "description": "Führt einen PowerShell-Befehl auf dem Windows-PC aus und gibt die Ausgabe zurück. "
                       "Für alles, wofür es kein eigenes Werkzeug gibt: Dateien/Ordner verwalten, Programme "
                       "installieren (winget), Systeminfos, Einstellungen, Prozesse usw. Der Nutzer muss jeden "
                       "Befehl bestätigen – erkläre in 'zweck' in einfachen Worten, was passiert. "
                       f"Python-Pakete installierst du mit: & '{sys.executable}' -m pip install PAKET",
        "input_schema": {
            "type": "object",
            "properties": {
                "befehl": {"type": "string", "description": "Der PowerShell-Befehl"},
                "zweck": {"type": "string", "description": "Kurz und verständlich: was der Befehl tut"},
            },
            "required": ["befehl", "zweck"],
        },
    },
    {
        "name": "werkzeug_erstellen",
        "description": "Baut ein neues, dauerhaftes Werkzeug für Jarvis (Python-Plugin), wenn der Nutzer das "
                       "möchte. Der Code muss eine Variable WERKZEUG (dict mit name, description, input_schema) "
                       "und eine Funktion ausfuehren(**eingaben) enthalten, die einen Text zurückgibt. Nur "
                       "Python-Standardbibliothek oder Pakete, die vorher mit befehl_ausfuehren installiert "
                       "wurden. Das Werkzeug steht ab der nächsten Frage zur Verfügung. Der Nutzer muss bestätigen. "
                       "Zum Ändern eines Plugins denselben Namen noch einmal verwenden.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Kurzer Name in Kleinbuchstaben mit _, z. B. 'bitcoin_preis'"},
                "zweck": {"type": "string", "description": "Was das Werkzeug kann, in einem Satz"},
                "python_code": {"type": "string", "description": "Kompletter Inhalt der Plugin-Datei"},
            },
            "required": ["name", "zweck", "python_code"],
        },
    },
]


BESCHREIBUNGEN.append({
    "name": "jarvis_aktualisieren",
    "description": "Holt die neueste Jarvis-Version von GitHub und installiert neue Pakete. Danach muss "
                   "Jarvis neu gestartet werden. Persönliche Dateien (.env, meine_einstellungen.py, Termine, "
                   "Plugins) bleiben erhalten.",
    "input_schema": {"type": "object", "properties": {}},
})


def jarvis_aktualisieren(bestaetigen):
    if not bestaetigen("update", "Jarvis aktualisieren (neueste Version von GitHub holen)",
                       "Deine .env, meine_einstellungen.py, Termine und Plugins bleiben erhalten."):
        return "Update abgebrochen."
    import updater
    try:
        archiv, url = updater.herunterladen()
        anzahl = updater.entpacken(archiv, updater.JARVIS_ORDNER)
        ok = updater.pakete_installieren()
    except Exception as fehler:
        return f"Update fehlgeschlagen: {fehler}"
    return (f"{anzahl} Dateien aktualisiert" + ("" if ok else ", aber pip meldete einen Fehler")
            + ". Bitte Jarvis jetzt neu starten (Fenster schließen und Verknüpfung öffnen).")


def befehl_ausfuehren(befehl, zweck, bestaetigen):
    if not IST_WINDOWS:
        return "Befehle ausführen geht nur unter Windows."
    if not einstellungen.BEFEHLE_OHNE_NACHFRAGE and not bestaetigen(
            "befehl", f"{zweck}", befehl):
        return "Der Nutzer hat den Befehl NICHT erlaubt. Nicht erneut versuchen, ohne nachzufragen."
    try:
        ergebnis = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + befehl],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(Path.home()), timeout=180, creationflags=0x08000000)
    except subprocess.TimeoutExpired:
        return "Der Befehl hat länger als 3 Minuten gedauert und wurde abgebrochen."
    ausgabe = (ergebnis.stdout or "").strip()
    fehler = (ergebnis.stderr or "").strip()
    text = f"Exit-Code {ergebnis.returncode}\n"
    if ausgabe:
        text += f"Ausgabe:\n{ausgabe[-6000:]}\n"
    if fehler:
        text += f"Fehler:\n{fehler[-3000:]}\n"
    return text if (ausgabe or fehler) else text + "(keine Ausgabe)"


def plugin_pruefen(name, code):
    """Prüft Name und Code, bevor gefragt wird. Gibt eine Fehlermeldung oder None zurück."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", name) or keyword.iskeyword(name):
        return "Ungültiger Name. Erlaubt: Kleinbuchstaben, Ziffern und _, z. B. 'wetter_morgen'."
    try:
        baum = ast.parse(code)
    except SyntaxError as fehler:
        return f"Der Code hat einen Syntaxfehler: {fehler}"
    namen = {n.name for n in baum.body if isinstance(n, ast.FunctionDef)}
    variablen = {t.id for n in baum.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    if "ausfuehren" not in namen or "WERKZEUG" not in variablen:
        return "Dem Code fehlt WERKZEUG = {...} oder die Funktion ausfuehren(**eingaben)."
    return None


def werkzeug_erstellen(name, zweck, python_code, bestaetigen, reservierte_namen=()):
    if name in reservierte_namen:
        return f"Den Namen '{name}' hat schon ein eingebautes Werkzeug. Bitte einen anderen wählen."
    problem = plugin_pruefen(name, python_code)
    if problem:
        return problem
    datei = PLUGIN_ORDNER / f"{name}.py"
    aktion = "ändern" if datei.exists() else "installieren"
    if not einstellungen.BEFEHLE_OHNE_NACHFRAGE and not bestaetigen(
            "werkzeug", f"Neues Werkzeug „{name}“ {aktion}: {zweck}", python_code):
        return "Der Nutzer hat das neue Werkzeug NICHT erlaubt."
    PLUGIN_ORDNER.mkdir(parents=True, exist_ok=True)
    datei.write_text(python_code, encoding="utf-8")
    try:
        modul = _laden(datei)
        modul.WERKZEUG["name"] = name
    except Exception as fehler:
        datei.unlink(missing_ok=True)
        return f"Das Werkzeug ließ sich nicht laden und wurde wieder entfernt: {fehler}"
    return f"Werkzeug „{name}“ gespeichert. Es ist ab der nächsten Frage verfügbar."


def _laden(datei):
    spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{datei.stem}", datei)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    if not isinstance(getattr(modul, "WERKZEUG", None), dict) or not callable(getattr(modul, "ausfuehren", None)):
        raise ValueError("WERKZEUG oder ausfuehren fehlt")
    return modul


def plugins_laden():
    """Lädt alle Plugins aus dem Ordner. Gibt {name: modul} zurück; kaputte Plugins werden übersprungen."""
    plugins = {}
    if not PLUGIN_ORDNER.exists():
        return plugins
    for datei in sorted(PLUGIN_ORDNER.glob("*.py")):
        try:
            modul = _laden(datei)
        except Exception as fehler:
            print(f"[Plugin {datei.name} übersprungen: {fehler}]")
            continue
        schema = dict(modul.WERKZEUG)
        schema["name"] = datei.stem
        schema.setdefault("description", datei.stem)
        schema.setdefault("input_schema", {"type": "object", "properties": {}})
        modul.WERKZEUG = schema
        plugins[datei.stem] = modul
    return plugins


def bestaetigung_konsole(art, beschreibung, details):
    """Bestätigung im schwarzen Fenster (Text-/Sprachmodus ohne Oberfläche)."""
    print("\n" + "=" * 60)
    print(f"JARVIS MÖCHTE: {beschreibung}")
    print("-" * 60)
    print(details if len(details) < 3000 else details[:3000] + "\n…")
    print("=" * 60)
    try:
        return input("Erlauben? (ja/nein): ").strip().lower() in ("j", "ja", "yes", "y")
    except EOFError:
        return False


def ist_ja(text):
    text = (text or "").lower().strip(" .!?")
    return any(text == w or text.startswith(w + " ") for w in ("ja", "jawohl", "mach", "okay", "ok", "los", "yes", "klar"))
