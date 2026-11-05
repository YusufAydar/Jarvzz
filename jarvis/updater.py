"""
Updater: holt die neueste Jarvis-Version von GitHub und ersetzt die Programmdateien.

Was NICHT überschrieben wird (deine persönlichen Sachen):
  .env                     – dein API-Schlüssel und MT5-Zugang
  meine_einstellungen.py   – deine eigenen Einstellungen
  daten/                   – Termine, Tagesstart usw.
  plugins/                 – Werkzeuge, die Jarvis sich selbst gebaut hat
  .venv/                   – die Installation

Starten: aktualisieren.bat doppelklicken – oder "Jarvis, aktualisiere dich" sagen.
"""

import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

JARVIS_ORDNER = Path(__file__).resolve().parent
# Zuerst der Entwicklungszweig, dann main (nach dem Mergen ist alles in main)
QUELLEN = [
    "https://github.com/YusufAydar/Jarvzz/archive/refs/heads/hyperliquid-analyse.zip",
    "https://github.com/YusufAydar/Jarvzz/archive/refs/heads/main.zip",
]
NICHT_ANFASSEN = {".env", "meine_einstellungen.py", "daten", "plugins", ".venv", "__pycache__"}


def herunterladen():
    for url in QUELLEN:
        try:
            with urllib.request.urlopen(url, timeout=60) as antwort:
                daten = antwort.read()
        except Exception as fehler:
            print(f"  {url} nicht erreichbar ({fehler})")
            continue
        archiv = zipfile.ZipFile(io.BytesIO(daten))
        # Im ZIP liegt alles unter "Jarvzz-<zweig>/jarvis/..."
        if any(n.split("/")[1:2] == ["jarvis"] for n in archiv.namelist()):
            return archiv, url
    raise RuntimeError("Keine Jarvis-Version auf GitHub gefunden.")


def entpacken(archiv, ziel):
    """Kopiert alle Dateien aus dem jarvis-Ordner des ZIPs nach ziel. Gibt die Anzahl zurück."""
    anzahl = 0
    for name in archiv.namelist():
        teile = name.split("/")
        if len(teile) < 3 or teile[1] != "jarvis" or name.endswith("/"):
            continue
        relativ = Path(*teile[2:])
        if relativ.parts[0] in NICHT_ANFASSEN:
            continue
        datei = ziel / relativ
        datei.parent.mkdir(parents=True, exist_ok=True)
        with archiv.open(name) as quelle, open(datei, "wb") as ausgabe:
            shutil.copyfileobj(quelle, ausgabe)
        anzahl += 1
    return anzahl


def pakete_installieren():
    return subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r",
                           str(JARVIS_ORDNER / "requirements.txt")]).returncode == 0


def main():
    print("Hole die neueste Jarvis-Version von GitHub ...")
    archiv, url = herunterladen()
    anzahl = entpacken(archiv, JARVIS_ORDNER)
    print(f"  {anzahl} Dateien aktualisiert (Quelle: {url})")
    print("Installiere neue Pakete ...")
    ok = pakete_installieren()
    print("Fertig! Starte Jarvis neu." if ok else "Dateien sind aktuell, aber pip meldete einen Fehler.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
