"""
Lange Kursgeschichte für Backtests – von Dukascopy (Schweizer Bank, kostenlos, ohne Konto).

Dukascopy stellt für jeden Handelstag eine Datei mit 1-Minuten-Kerzen bereit:
  https://datafeed.dukascopy.com/datafeed/<SYMBOL>/<JAHR>/<MONAT-1>/<TAG>/BID_candles_min_1.bi5
Die Datei ist LZMA-gepackt; jede Kerze hat 24 Byte: Sekunden seit Tagesbeginn (UTC), Open, Close,
Low, High (ganze Zahlen, Preis * Faktor) und das Volumen.

Wir machen daraus 15-Minuten-Kerzen und speichern sie pro Tag in daten/historie/ – beim zweiten
Backtest muss also nichts mehr heruntergeladen werden.
"""

import lzma
import struct
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import einstellungen

URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{jahr:04d}/{monat:02d}/{tag:02d}/BID_candles_min_1.bi5"
# Unser Name -> (Dukascopy-Name, plausibler Preisbereich zum Erkennen des Preis-Faktors)
SYMBOLE = {
    "XAUUSD": ("XAUUSD", (300, 20000)), "GOLD": ("XAUUSD", (300, 20000)),
    "XAGUSD": ("XAGUSD", (3, 300)),
    "EURUSD": ("EURUSD", (0.5, 2.5)), "GBPUSD": ("GBPUSD", (0.5, 3)), "USDJPY": ("USDJPY", (50, 300)),
    "AUDUSD": ("AUDUSD", (0.3, 1.5)), "USDCHF": ("USDCHF", (0.5, 2)), "USDCAD": ("USDCAD", (0.8, 2)),
    "US100": ("USATECHIDXUSD", (2000, 60000)), "NAS100": ("USATECHIDXUSD", (2000, 60000)),
    "US500": ("USA500IDXUSD", (500, 20000)), "US30": ("USA30IDXUSD", (5000, 100000)),
    "GER40": ("DEUIDXEUR", (5000, 60000)), "DAX": ("DEUIDXEUR", (5000, 60000)),
    "BTCUSD": ("BTCUSD", (1000, 500000)),
}
FAKTOREN = (100000, 1000, 100, 10, 1)
ORDNER = einstellungen.DATEN_ORDNER / "historie"


def kerzen_aus_bi5(roh, tag_start):
    """Entpackt eine Dukascopy-Tagesdatei zu 1-Minuten-Kerzen (Preise noch als ganze Zahlen)."""
    if not roh:
        return []
    daten = lzma.decompress(roh)
    kerzen = []
    for i in range(0, len(daten) - 23, 24):
        sekunden, o, c, l, h, volumen = struct.unpack(">IIIIIf", daten[i:i + 24])
        if volumen <= 0:  # Markt geschlossen (Dukascopy füllt diese Zeiten mit "leeren" Kerzen)
            continue
        kerzen.append({"zeit": tag_start + sekunden, "open": o, "high": h, "low": l, "close": c})
    return kerzen


def faktor_finden(kerzen, bereich):
    """Findet den Preis-Faktor, mit dem die Kurse im plausiblen Bereich liegen."""
    if not kerzen:
        return None
    mitte = sorted(k["close"] for k in kerzen)[len(kerzen) // 2]
    for f in FAKTOREN:
        if bereich[0] <= mitte / f <= bereich[1]:
            return f
    return None


def zu_m15(kerzen_1m):
    """1-Minuten-Kerzen -> 15-Minuten-Kerzen (an UTC-Viertelstunden ausgerichtet)."""
    bloecke = {}
    for k in kerzen_1m:
        b = k["zeit"] // 900
        x = bloecke.get(b)
        if x is None:
            bloecke[b] = dict(k, zeit=b * 900)
        else:
            x["high"], x["low"], x["close"] = max(x["high"], k["high"]), min(x["low"], k["low"]), k["close"]
    return [bloecke[b] for b in sorted(bloecke)]


def _tag_laden(dukas_symbol, tag, bereich, ordner):
    """Lädt einen Tag (aus dem Zwischenspeicher oder von Dukascopy). Gibt M15-Kerzen zurück."""
    datei = ordner / dukas_symbol / f"{tag.isoformat()}.csv"
    if datei.exists():
        zeilen = datei.read_text(encoding="utf-8").split()
        return [dict(zip(("zeit", "open", "high", "low", "close"), (int(z.split(",")[0]),
                     *map(float, z.split(",")[1:])))) for z in zeilen]
    url = URL.format(sym=dukas_symbol, jahr=tag.year, monat=tag.month - 1, tag=tag.day)
    anfrage = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            roh = antwort.read()
    except urllib.error.HTTPError as fehler:
        if fehler.code == 404:
            roh = b""
        else:
            raise
    start = int(datetime(tag.year, tag.month, tag.day, tzinfo=timezone.utc).timestamp())
    roh_kerzen = kerzen_aus_bi5(roh, start)
    faktor = faktor_finden(roh_kerzen, bereich) if roh_kerzen else 1
    if roh_kerzen and faktor is None:
        raise ValueError(f"Preis-Faktor für {dukas_symbol} nicht erkennbar")
    m15 = [{"zeit": k["zeit"], "open": k["open"] / faktor, "high": k["high"] / faktor,
            "low": k["low"] / faktor, "close": k["close"] / faktor} for k in zu_m15(roh_kerzen)]
    if tag < date.today() - timedelta(days=1):  # abgeschlossene Tage dauerhaft speichern
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text("\n".join(f"{k['zeit']},{k['open']},{k['high']},{k['low']},{k['close']}" for k in m15),
                         encoding="utf-8")
    return m15


def m15_laden(symbol, tage=730, ordner=None, fortschritt=None):
    """
    Lädt die letzten `tage` Kalendertage als M15-Kerzen (ältester zuerst).
    fortschritt: optionale Funktion(erledigt, gesamt) für eine Anzeige.
    """
    eintrag = SYMBOLE.get(symbol.upper().replace("/", "").replace(".CASH", ""))
    if not eintrag:
        raise ValueError(f"Für {symbol} gibt es keine Dukascopy-Historie.")
    dukas_symbol, bereich = eintrag
    ordner = Path(ordner or ORDNER)
    heute = datetime.now(timezone.utc).date()
    alle_tage = [heute - timedelta(days=i) for i in range(tage, 0, -1)]
    handelstage = [t for t in alle_tage if t.weekday() != 5]  # samstags ist alles zu
    ergebnis = [None] * len(handelstage)
    erledigt = [0]

    def laden(i):
        ergebnis[i] = _tag_laden(dukas_symbol, handelstage[i], bereich, ordner)
        erledigt[0] += 1
        if fortschritt:
            fortschritt(erledigt[0], len(handelstage))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(laden, range(len(handelstage))))
    kerzen = [k for tag in ergebnis for k in tag]
    if not kerzen:
        raise ValueError(f"Dukascopy hat keine Daten für {symbol} geliefert.")
    return kerzen
