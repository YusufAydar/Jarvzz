"""
Spricht mit der öffentlichen Hyperliquid-API.

Hier passiert nur das Herunterladen von Daten – keine Auswertung.
Es werden nur Python-Bordmittel benutzt, du musst also nichts extra installieren.
"""

import json
import time
import urllib.error
import urllib.request

import config

# Adresse für fast alle Abfragen (Trades, Positionen, ...)
INFO_URL = "https://api.hyperliquid.xyz/info"
# Adresse der öffentlichen Rangliste (Leaderboard)
RANGLISTE_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"

# Hyperliquid liefert pro Anfrage höchstens 2000 Trades
MAX_FILLS_PRO_ANFRAGE = 2000

KOPFZEILEN = {"Content-Type": "application/json", "User-Agent": "jarvzz-analyse"}


def _anfrage(url, daten=None, versuche=6):
    """
    Schickt eine Anfrage und gibt die Antwort als Python-Objekt zurück.
    Bei Problemen (z. B. "zu viele Anfragen") wird gewartet und neu versucht.
    """
    for versuch in range(versuche):
        try:
            if daten is None:
                anfrage = urllib.request.Request(url, headers=KOPFZEILEN)
            else:
                anfrage = urllib.request.Request(
                    url, data=json.dumps(daten).encode("utf-8"),
                    headers=KOPFZEILEN, method="POST",
                )
            with urllib.request.urlopen(anfrage, timeout=120) as antwort:
                ergebnis = json.loads(antwort.read())
            time.sleep(config.PAUSE_ZWISCHEN_ANFRAGEN)
            return ergebnis
        except urllib.error.HTTPError as fehler:
            # 429 = zu viele Anfragen, 5xx = Serverproblem -> warten und nochmal
            if fehler.code == 429 or fehler.code >= 500:
                wartezeit = 2 ** versuch * 2
                print(f"  API meldet {fehler.code}, warte {wartezeit} s ...")
                time.sleep(wartezeit)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as fehler:
            wartezeit = 2 ** versuch * 2
            print(f"  Verbindungsproblem ({fehler}), warte {wartezeit} s ...")
            time.sleep(wartezeit)
    raise RuntimeError(f"API nicht erreichbar nach {versuche} Versuchen: {url}")


def _zahl(wert):
    """Macht aus einem Text wie "123.45" eine Zahl. Leere Werte werden 0."""
    try:
        return float(wert)
    except (TypeError, ValueError):
        return 0.0


def lade_rangliste():
    """
    Lädt die komplette öffentliche Rangliste.
    Gibt eine Liste von Einträgen zurück, jeder Eintrag ist ein Wörterbuch (dict).
    """
    daten = _anfrage(RANGLISTE_URL)
    eintraege = []
    for zeile in daten.get("leaderboardRows", []):
        # "windowPerformances" sieht so aus: [["day", {...}], ["week", {...}], ...]
        leistung = {name: werte for name, werte in zeile.get("windowPerformances", [])}
        eintraege.append({
            "wallet": zeile["ethAddress"].lower(),
            "name": zeile.get("displayName"),
            "kontowert": _zahl(zeile.get("accountValue")),
            "pnl_tag": _zahl(leistung.get("day", {}).get("pnl")),
            "pnl_woche": _zahl(leistung.get("week", {}).get("pnl")),
            "pnl_monat": _zahl(leistung.get("month", {}).get("pnl")),
            "pnl_gesamt": _zahl(leistung.get("allTime", {}).get("pnl")),
            "roi_monat": _zahl(leistung.get("month", {}).get("roi")),
            "volumen_monat": _zahl(leistung.get("month", {}).get("vlm")),
        })
    return eintraege


def waehle_top_trader(rangliste, anzahl, zeitraum="month", min_kontowert=0):
    """
    Sortiert die Rangliste nach Gewinn im gewählten Zeitraum
    und gibt die besten `anzahl` Wallets zurück.
    """
    feld = {"day": "pnl_tag", "week": "pnl_woche",
            "month": "pnl_monat", "allTime": "pnl_gesamt"}[zeitraum]
    passende = [e for e in rangliste if e["kontowert"] >= min_kontowert]
    passende.sort(key=lambda e: e[feld], reverse=True)
    top = passende[:anzahl]
    for rang, eintrag in enumerate(top, start=1):
        eintrag["rang"] = rang
    return top


def lade_fills(wallet, ab_zeitpunkt_ms=0):
    """
    Lädt alle Trades ("Fills") einer Wallet ab einem Zeitpunkt (in Millisekunden).
    Weil die API pro Anfrage nur 2000 Trades liefert, wird seitenweise geladen.

    Achtung: Hyperliquid gibt pro Wallet höchstens die letzten 10.000 Trades heraus.
    Bei sehr aktiven Tradern fehlt also die ältere Historie.
    """
    alle = []
    start = ab_zeitpunkt_ms
    for _ in range(50):  # Sicherheitsgrenze, damit es nie endlos läuft
        teil = _anfrage(INFO_URL, {
            "type": "userFillsByTime",
            "user": wallet,
            "startTime": int(start),
            "aggregateByTime": False,
        })
        if not teil:
            break
        alle.extend(teil)
        if len(teil) < MAX_FILLS_PRO_ANFRAGE:
            break
        neuester = max(f["time"] for f in teil)
        # Nächste Seite ab dem neuesten Zeitpunkt (doppelte Trades filtert die Datenbank)
        start = neuester if neuester > start else start + 1
    return alle


def lade_positionen(wallet):
    """
    Lädt die aktuell offenen Positionen und den Kontostand einer Wallet.
    Hier steht auch der Hebel, den der Trader gerade benutzt.
    """
    daten = _anfrage(INFO_URL, {"type": "clearinghouseState", "user": wallet})
    positionen = []
    for eintrag in daten.get("assetPositions", []):
        pos = eintrag.get("position", {})
        hebel = pos.get("leverage") or {}
        positionen.append({
            "coin": pos.get("coin"),
            "groesse": _zahl(pos.get("szi")),           # positiv = Long, negativ = Short
            "einstiegspreis": _zahl(pos.get("entryPx")),
            "positionswert": _zahl(pos.get("positionValue")),
            "hebel": _zahl(hebel.get("value")),
            "hebel_typ": hebel.get("type"),             # "cross" oder "isolated"
            "unrealisiert": _zahl(pos.get("unrealizedPnl")),
        })
    kontowert = _zahl(daten.get("marginSummary", {}).get("accountValue"))
    return positionen, kontowert
