"""
Die Verbindung zwischen Jarvis (auf deinem PC) und Claude (dem Entwickler in Claude Code).
Beide treffen sich im GitHub-Repository.

Jarvis -> Claude:
    Jarvis lädt seine EIGENEN Änderungen (selbst geänderte Programmdateien, selbstgebaute Werkzeuge,
    meine_einstellungen.py) mit einem Bericht in den GitHub-Zweig "jarvis-pc" (Ordner jarvis-pc/).
    Claude liest das, bevor er etwas an Jarvis ändert (so steht es in CLAUDE.md).
    Niemals hochgeladen: .env (Schlüssel/Passwörter), daten/ (Termine, Tagebuch), Sicherungen.
    Zusätzlich prüft ein Geheimnis-Filter jede Datei auf Schlüssel und Passwörter.

Claude -> Jarvis:
    Claude trägt jede Änderung in NEUIGKEITEN.md ein. Jarvis vergleicht seine Datei mit der auf
    GitHub, meldet "Update verfügbar" und kennt nach dem Update seine neuen Fähigkeiten.

Zum Hochladen braucht Jarvis einen GitHub-Token mit Schreibrecht (GITHUB_TOKEN in .env, siehe README).
"""

import base64
import hashlib
import json
import os
import platform
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = "YusufAydar/Jarvzz"
JARVIS_ZWEIG = "jarvis-pc"
ENTWICKLUNGS_ZWEIGE = ["hyperliquid-analyse", "main"]  # hier veröffentlicht Claude
JARVIS_ORDNER = Path(__file__).resolve().parent
NIE_HOCHLADEN_ORDNER = {".venv", "__pycache__", "sicherungen", "daten"}
NIE_HOCHLADEN_DATEIEN = {".env"}
GEHEIMNIS_MUSTER = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?m)^\s*[A-Z0-9_]*(PASS|PASSWORT|PASSWORD|TOKEN|SECRET|API_KEY)[A-Z0-9_]*\s*=\s*['\"]?[^\s'\"]{6,}"),
    re.compile(r"(?i)(passwort|password|api_key|secret)\s*=\s*['\"][^'\"]{6,}['\"]"),
]


class SyncFehler(Exception):
    pass


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def _token():
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    datei = JARVIS_ORDNER / ".env"
    if datei.exists():
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            if zeile.strip().startswith("GITHUB_TOKEN="):
                return zeile.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _api(methode, pfad, daten=None, token=None):
    token = token or _token()
    if not token:
        raise SyncFehler("Kein GITHUB_TOKEN in der .env – siehe README, Abschnitt 'Verbindung zu Claude'.")
    anfrage = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{pfad}", method=methode,
        data=json.dumps(daten).encode() if daten is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "jarvis-sync", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            inhalt = antwort.read()
            return json.loads(inhalt) if inhalt else {}
    except urllib.error.HTTPError as fehler:
        if fehler.code == 404 and methode == "GET":
            return None
        if fehler.code in (401, 403):
            raise SyncFehler("GitHub lehnt den Token ab. Hat er bei 'Contents' das Recht 'Read and write' "
                             "für das Repository Jarvzz?") from fehler
        raise SyncFehler(f"GitHub-Fehler {fehler.code}: {fehler.read()[:200]!r}") from fehler


def enthaelt_geheimnis(text):
    return any(m.search(text) for m in GEHEIMNIS_MUSTER)


# ---------------------------------------------------------------------------
# Jarvis -> Claude
# ---------------------------------------------------------------------------

def lokale_aenderungen(ordner=JARVIS_ORDNER):
    """
    Findet Dateien, die NICHT von Claude veröffentlicht wurden:
      "geändert" = eine Programmdatei, die du/Jarvis verändert habt
      "neu"      = eine Datei, die es bei Claude nicht gibt (z. B. ein selbstgebautes Werkzeug)
    Gibt eine Liste von dicts (pfad, status, inhalt) zurück und eine Liste übersprungener Dateien.
    """
    ordner = Path(ordner)
    try:
        bekannte = json.loads((ordner / "versionen.json").read_text(encoding="utf-8"))
    except Exception:
        bekannte = {}
    gefunden, uebersprungen = [], []
    for datei in sorted(ordner.rglob("*")):
        if not datei.is_file():
            continue
        relativ = datei.relative_to(ordner)
        if set(relativ.parts) & NIE_HOCHLADEN_ORDNER or relativ.name in NIE_HOCHLADEN_DATEIEN:
            continue
        if relativ.suffix in (".neu", ".pyc") or relativ.name == "versionen.json":
            continue
        pfad = relativ.as_posix()
        inhalt = datei.read_bytes()
        if pfad in bekannte:
            if hashlib.sha256(inhalt).hexdigest() in bekannte[pfad]:
                continue  # unverändert
            status = "geändert"
        else:
            status = "neu"
        if len(inhalt) > 1_000_000:
            uebersprungen.append((pfad, "zu groß"))
            continue
        try:
            text = inhalt.decode("utf-8")
        except UnicodeDecodeError:
            uebersprungen.append((pfad, "keine Textdatei"))
            continue
        if enthaelt_geheimnis(text):
            uebersprungen.append((pfad, "enthält wohl ein Passwort oder einen Schlüssel"))
            continue
        gefunden.append({"pfad": pfad, "status": status, "inhalt": inhalt})
    return gefunden, uebersprungen


def bericht_text(dateien, uebersprungen, nachricht):
    zeilen = [f"# Bericht von Jarvis – {datetime.now():%d.%m.%Y %H:%M}", "",
              f"PC: {platform.node()} ({platform.system()} {platform.release()})", "",
              "## Nachricht von Jarvis", "", nachricht or "(keine Nachricht)", "",
              "## Eigene Änderungen auf dem PC", ""]
    zeilen += [f"- `{d['pfad']}` – {d['status']}" for d in dateien] or ["- keine"]
    if uebersprungen:
        zeilen += ["", "## Nicht hochgeladen", ""] + [f"- `{p}` – {grund}" for p, grund in uebersprungen]
    zeilen += ["", "Die Dateien liegen in diesem Zweig unter `jarvis-pc/` (gleiche Ordnerstruktur wie `jarvis/`)."]
    return "\n".join(zeilen) + "\n"


def hochladen(nachricht="", ordner=JARVIS_ORDNER, dateien=None, uebersprungen=None):
    """Lädt die eigenen Änderungen als EIN Commit in den Zweig jarvis-pc. Gibt eine Zusammenfassung zurück."""
    if dateien is None:
        dateien, uebersprungen = lokale_aenderungen(ordner)
    uebersprungen = uebersprungen or []
    ref = _api("GET", f"git/ref/heads/{JARVIS_ZWEIG}")
    if ref is None:
        for zweig in ENTWICKLUNGS_ZWEIGE:
            ref_basis = _api("GET", f"git/ref/heads/{zweig}")
            if ref_basis:
                break
        else:
            raise SyncFehler("Im Repository wurde kein Zweig gefunden.")
        eltern = ref_basis["object"]["sha"]
    else:
        eltern = ref["object"]["sha"]
    basis_baum = _api("GET", f"git/commits/{eltern}")["tree"]["sha"]
    # Alte Dateien unter jarvis-pc/, die es nicht mehr gibt, werden entfernt
    alt = _api("GET", f"git/trees/{basis_baum}?recursive=1") or {"tree": []}
    neue_pfade = {f"jarvis-pc/{d['pfad']}" for d in dateien} | {"jarvis-pc/BERICHT.md"}
    eintraege = [{"path": e["path"], "mode": "100644", "type": "blob", "sha": None}
                 for e in alt.get("tree", []) if e["type"] == "blob"
                 and e["path"].startswith("jarvis-pc/") and e["path"] not in neue_pfade]
    for d in dateien + [{"pfad": "BERICHT.md", "inhalt": bericht_text(dateien, uebersprungen, nachricht).encode()}]:
        blob = _api("POST", "git/blobs", {"content": base64.b64encode(d["inhalt"]).decode(), "encoding": "base64"})
        eintraege.append({"path": f"jarvis-pc/{d['pfad']}", "mode": "100644", "type": "blob", "sha": blob["sha"]})
    baum = _api("POST", "git/trees", {"base_tree": basis_baum, "tree": eintraege})
    commit = _api("POST", "git/commits", {"message": f"Jarvis-Bericht: {nachricht[:60] or 'eigene Änderungen'}",
                                          "tree": baum["sha"], "parents": [eltern]})
    if ref is None:
        _api("POST", "git/refs", {"ref": f"refs/heads/{JARVIS_ZWEIG}", "sha": commit["sha"]})
    else:
        _api("PATCH", f"git/refs/heads/{JARVIS_ZWEIG}", {"sha": commit["sha"]})
    return {"dateien": [d["pfad"] for d in dateien], "uebersprungen": uebersprungen, "commit": commit["sha"][:7]}


# ---------------------------------------------------------------------------
# Claude -> Jarvis
# ---------------------------------------------------------------------------

def neuigkeiten_auswerten(text):
    """Zerlegt NEUIGKEITEN.md in Einträge: [{"kopf": "2026-11-05 · Titel", "text": "..."}], neueste zuerst."""
    eintraege, aktuell = [], None
    for zeile in text.splitlines():
        if zeile.startswith("## "):
            aktuell = {"kopf": zeile[3:].strip(), "text": ""}
            eintraege.append(aktuell)
        elif aktuell is not None:
            aktuell["text"] += zeile + "\n"
    for e in eintraege:
        e["text"] = e["text"].strip()
    return eintraege


def neuigkeiten_lokal(ordner=JARVIS_ORDNER):
    try:
        return neuigkeiten_auswerten((Path(ordner) / "NEUIGKEITEN.md").read_text(encoding="utf-8"))
    except Exception:
        return []


def neuigkeiten_github():
    """Liest NEUIGKEITEN.md direkt von GitHub (öffentlich oder mit Token)."""
    token = _token()
    for zweig in ENTWICKLUNGS_ZWEIGE:
        if token:
            url = f"https://api.github.com/repos/{REPO}/contents/jarvis/NEUIGKEITEN.md?ref={zweig}"
            kopf = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw", "User-Agent": "jarvis"}
        else:
            url = f"https://raw.githubusercontent.com/{REPO}/{zweig}/jarvis/NEUIGKEITEN.md"
            kopf = {"User-Agent": "jarvis"}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=kopf), timeout=20) as antwort:
                return neuigkeiten_auswerten(antwort.read().decode("utf-8"))
        except Exception:
            continue
    raise SyncFehler("NEUIGKEITEN.md auf GitHub nicht erreichbar.")


def update_pruefen(ordner=JARVIS_ORDNER):
    """Gibt die Einträge zurück, die auf GitHub stehen, aber hier noch nicht installiert sind."""
    lokal = {e["kopf"] for e in neuigkeiten_lokal(ordner)}
    return [e for e in neuigkeiten_github() if e["kopf"] not in lokal]


def fuer_grundanweisung(anzahl=4, ordner=JARVIS_ORDNER):
    """Kurzfassung der neuesten Änderungen für Jarvis' Grundanweisung (damit er sie kennt)."""
    eintraege = neuigkeiten_lokal(ordner)[:anzahl]
    if not eintraege:
        return ""
    teile = [f"- {e['kopf']}: {' '.join(e['text'].split())[:400]}" for e in eintraege]
    return ("\nNeueste Änderungen an dir (von Claude, deinem Entwickler) – du kennst diese Fähigkeiten:\n"
            + "\n".join(teile) + "\n")
