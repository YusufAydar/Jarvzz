"""
Wirtschaftskalender (News): wichtige Termine wie Zinsentscheide, NFP oder CPI.
Gerade bei FTMO wichtig – kurz vor und nach starken News schwanken die Kurse heftig.

Quelle: öffentlicher Wochen-Kalender von ForexFactory (faireconomy.media), ohne Konto.
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
WICHTIGKEIT = {"High": "HOCH", "Medium": "mittel", "Low": "niedrig", "Holiday": "Feiertag"}


def laden():
    anfrage = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(anfrage, timeout=20) as antwort:
        return json.loads(antwort.read())


def termine(daten, von, bis, nur_wichtig=True, waehrungen=None):
    """Filtert die Termine im Zeitraum [von, bis) – beides datetime mit Zeitzone."""
    ergebnis = []
    for e in daten:
        try:
            zeit = datetime.fromisoformat(e["date"])
        except (KeyError, ValueError):
            continue
        if not (von <= zeit < bis):
            continue
        if nur_wichtig and e.get("impact") != "High":
            continue
        if waehrungen and e.get("country") not in waehrungen:
            continue
        ergebnis.append({"zeit": zeit, "titel": e.get("title", ""), "waehrung": e.get("country", ""),
                         "wichtig": WICHTIGKEIT.get(e.get("impact"), e.get("impact")),
                         "prognose": e.get("forecast") or "–", "vorher": e.get("previous") or "–"})
    return sorted(ergebnis, key=lambda x: x["zeit"])


def zusammenfassung(liste, titel):
    if not liste:
        return f"{titel}: keine wichtigen Termine."
    zeilen = [titel + " (Ortszeit):"]
    for e in liste:
        lokal = e["zeit"].astimezone()
        zeilen.append(f"{lokal:%a %d.%m. %H:%M} {e['waehrung']} {e['titel']} [{e['wichtig']}] "
                      f"Prognose {e['prognose']}, vorher {e['vorher']}")
    return "\n".join(zeilen)


def heute_und_morgen(nur_wichtig=True, waehrungen=None, jetzt=None):
    jetzt = jetzt or datetime.now(timezone.utc)
    anfang = jetzt.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return termine(laden(), anfang, anfang + timedelta(days=2), nur_wichtig, waehrungen)
