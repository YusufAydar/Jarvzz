"""
Erzeugt jarvis/versionen.json: für jede Jarvis-Datei die Prüfsummen ALLER bisher veröffentlichten
Versionen. Der Updater erkennt daran, ob eine Datei auf dem PC unverändert ist (dann darf sie
ersetzt werden) oder vom Nutzer bzw. von Jarvis selbst geändert wurde (dann bleibt sie stehen).

Vor jedem Commit ausführen:  python werkzeuge_entwicklung/versionen_erzeugen.py
"""

import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ZIEL = REPO / "jarvis" / "versionen.json"


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=True).stdout


def main():
    bekannte = {}
    for commit in git("log", "--format=%H", "--", "jarvis").decode().split():
        for pfad in git("ls-tree", "-r", "--name-only", commit, "jarvis").decode().splitlines():
            relativ = pfad[len("jarvis/"):]
            inhalt = git("show", f"{commit}:{pfad}")
            bekannte.setdefault(relativ, set()).add(hashlib.sha256(inhalt).hexdigest())
    # Der aktuelle Stand im Arbeitsordner gehört auch dazu (nur Dateien, die ins Repo kommen)
    aktuell = git("ls-files", "--cached", "--others", "--exclude-standard", "jarvis").decode().splitlines()
    for pfad in aktuell:
        datei = REPO / pfad
        if datei.is_file() and datei != ZIEL:
            relativ = pfad[len("jarvis/"):]
            bekannte.setdefault(relativ, set()).add(hashlib.sha256(datei.read_bytes()).hexdigest())
    ZIEL.write_text(json.dumps({k: sorted(v) for k, v in sorted(bekannte.items())}, indent=0), encoding="utf-8")
    print(f"{len(bekannte)} Dateien, {sum(len(v) for v in bekannte.values())} Versionen -> {ZIEL}")


if __name__ == "__main__":
    main()
