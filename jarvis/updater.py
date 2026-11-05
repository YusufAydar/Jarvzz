"""
Updater: holt die neueste Jarvis-Version von GitHub – ohne deine Sachen kaputtzumachen.

1. Vorher wird der ganze Jarvis-Ordner als ZIP gesichert (Ordner sicherungen/).
2. Nie angefasst: .env, meine_einstellungen.py, daten/, plugins/, .venv/, sicherungen/
3. Dateien, die du oder Jarvis selbst geändert habt (z. B. ein eigenes Design), bleiben stehen.
   Die neue Version liegt dann daneben als "<name>.neu" – du entscheidest selbst.
   (Erkannt wird das über versionen.json: alle Prüfsummen der bisher veröffentlichten Versionen.)

Starten: aktualisieren.bat doppelklicken – oder "Jarvis, aktualisiere dich" sagen.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

JARVIS_ORDNER = Path(__file__).resolve().parent
QUELLEN = [
    "https://github.com/YusufAydar/Jarvzz/archive/refs/heads/hyperliquid-analyse.zip",
    "https://github.com/YusufAydar/Jarvzz/archive/refs/heads/main.zip",
]
NICHT_ANFASSEN = {".env", "meine_einstellungen.py", "daten", "plugins", ".venv", "__pycache__", "sicherungen"}


def _env_lesen():
    """Liest jarvis/.env (für den GitHub-Token bei privaten Repos)."""
    werte = {}
    datei = JARVIS_ORDNER / ".env"
    if datei.exists():
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            if "=" in zeile and not zeile.strip().startswith("#"):
                name, wert = zeile.split("=", 1)
                werte[name.strip()] = wert.strip().strip('"').strip("'")
    return werte


def quellen():
    """Bei privatem Repo (GITHUB_TOKEN in .env) über die GitHub-API, sonst die öffentlichen ZIP-Links."""
    token = os.environ.get("GITHUB_TOKEN") or _env_lesen().get("GITHUB_TOKEN")
    if token:
        kopf = {"Authorization": f"Bearer {token}", "User-Agent": "jarvis-updater"}
        return [(f"https://api.github.com/repos/YusufAydar/Jarvzz/zipball/{zweig}", kopf)
                for zweig in ("hyperliquid-analyse", "main")]
    return [(url, {"User-Agent": "jarvis-updater"}) for url in QUELLEN]


def herunterladen():
    for url, kopf in quellen():
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=kopf), timeout=60) as antwort:
                daten = antwort.read()
        except Exception as fehler:
            print(f"  {url} nicht erreichbar ({fehler})")
            continue
        archiv = zipfile.ZipFile(io.BytesIO(daten))
        if any(n.split("/")[1:2] == ["jarvis"] for n in archiv.namelist()):
            return archiv, url
    raise RuntimeError("Keine Jarvis-Version auf GitHub gefunden. Ist das Repository privat? Dann "
                       "GITHUB_TOKEN in jarvis/.env eintragen (siehe README, Abschnitt Updates).")


def _pruefsumme(daten):
    return hashlib.sha256(daten).hexdigest()


def sichern(ordner):
    """Packt den Jarvis-Ordner (ohne .venv, Caches und alte Sicherungen) in ein ZIP."""
    ziel = ordner / "sicherungen" / f"sicherung_{datetime.now():%Y%m%d_%H%M%S}.zip"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
        for datei in ordner.rglob("*"):
            teile = datei.relative_to(ordner).parts
            if datei.is_file() and not {".venv", "__pycache__", "sicherungen"} & set(teile):
                z.write(datei, Path(*teile))
    return ziel


def entpacken(archiv, ziel):
    """
    Spielt die neue Version ein. Gibt (aktualisiert, behalten) zurück:
    aktualisiert = Anzahl ersetzter/neuer Dateien, behalten = Liste selbst geänderter Dateien.
    """
    dateien = {}
    for name in archiv.namelist():
        teile = name.split("/")
        if len(teile) < 3 or teile[1] != "jarvis" or name.endswith("/"):
            continue
        relativ = Path(*teile[2:])
        if relativ.parts[0] in NICHT_ANFASSEN:
            continue
        dateien[relativ] = archiv.read(name)
    bekannte = {}
    if Path("versionen.json") in dateien:
        bekannte = json.loads(dateien[Path("versionen.json")])

    aktualisiert, behalten = 0, []
    for relativ, inhalt in dateien.items():
        datei = ziel / relativ
        if datei.exists():
            vorhanden = datei.read_bytes()
            if vorhanden == inhalt:
                continue
            if _pruefsumme(vorhanden) not in bekannte.get(relativ.as_posix(), []):
                # Selbst geändert -> stehen lassen, neue Version daneben legen
                Path(str(datei) + ".neu").write_bytes(inhalt)
                behalten.append(relativ.as_posix())
                continue
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_bytes(inhalt)
        aktualisiert += 1
    return aktualisiert, behalten


def pakete_installieren():
    return subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r",
                           str(JARVIS_ORDNER / "requirements.txt")]).returncode == 0


def bericht(aktualisiert, behalten, sicherung):
    text = f"{aktualisiert} Dateien aktualisiert. Sicherung: {sicherung.name}."
    if behalten:
        text += (" Diese Dateien hast du selbst geändert, sie wurden NICHT überschrieben (neue Version "
                 "liegt daneben als .neu): " + ", ".join(behalten))
    return text


def main():
    print("Hole die neueste Jarvis-Version von GitHub ...")
    archiv, url = herunterladen()
    sicherung = sichern(JARVIS_ORDNER)
    print(f"  Sicherung angelegt: {sicherung}")
    aktualisiert, behalten = entpacken(archiv, JARVIS_ORDNER)
    print("  " + bericht(aktualisiert, behalten, sicherung))
    print("Installiere neue Pakete ...")
    ok = pakete_installieren()
    print("Fertig! Starte Jarvis neu." if ok else "Dateien sind aktuell, aber pip meldete einen Fehler.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
