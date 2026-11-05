"""
Kursquellen ohne MetaTrader 5.

- Yahoo Finance: Kerzen für Gold, Forex und Indizes (kostenlos, ohne Konto).
  Gold kommt vom Gold-Future (GC=F), Indizes von den Futures (z. B. YM=F für den Dow).
  Die Preise liegen deshalb leicht neben den CFD-Preisen bei FTMO – für Trend und
  Indikatoren reicht das, für exakte Einstiege zählt der Preis bei deinem Broker.
- TradingView-Kürzel (für die TradingView-Analyse) stehen auch hier.
"""

import json
import urllib.parse
import urllib.request

# Name, wie du ihn sagst  ->  (Yahoo-Kürzel, TradingView-Kürzel)
SYMBOLE = {
    "XAUUSD": ("GC=F", "OANDA:XAUUSD"), "GOLD": ("GC=F", "OANDA:XAUUSD"),
    "XAGUSD": ("SI=F", "OANDA:XAGUSD"), "SILBER": ("SI=F", "OANDA:XAGUSD"),
    "EURUSD": ("EURUSD=X", "OANDA:EURUSD"), "GBPUSD": ("GBPUSD=X", "OANDA:GBPUSD"),
    "USDJPY": ("JPY=X", "OANDA:USDJPY"), "AUDUSD": ("AUDUSD=X", "OANDA:AUDUSD"),
    "USDCHF": ("CHF=X", "OANDA:USDCHF"), "USDCAD": ("CAD=X", "OANDA:USDCAD"),
    "GBPJPY": ("GBPJPY=X", "OANDA:GBPJPY"), "EURJPY": ("EURJPY=X", "OANDA:EURJPY"),
    "US30": ("YM=F", "OANDA:US30USD"), "DOW": ("YM=F", "OANDA:US30USD"),
    "US100": ("NQ=F", "OANDA:NAS100USD"), "NAS100": ("NQ=F", "OANDA:NAS100USD"), "NASDAQ": ("NQ=F", "OANDA:NAS100USD"),
    "US500": ("ES=F", "OANDA:SPX500USD"), "SP500": ("ES=F", "OANDA:SPX500USD"),
    "GER40": ("^GDAXI", "OANDA:DE30EUR"), "DAX": ("^GDAXI", "OANDA:DE30EUR"),
    "USOIL": ("CL=F", "OANDA:WTICOUSD"), "OEL": ("CL=F", "OANDA:WTICOUSD"),
    "BTCUSD": ("BTC-USD", "BITSTAMP:BTCUSD"), "BITCOIN": ("BTC-USD", "BITSTAMP:BTCUSD"),
    "ETHUSD": ("ETH-USD", "BITSTAMP:ETHUSD"), "SOLUSD": ("SOL-USD", "COINBASE:SOLUSD"),
}

# Zeitrahmen -> (Yahoo-Intervall, Zeitraum, wie viele Kerzen zusammengefasst werden)
YAHOO_ZEITRAHMEN = {"M1": ("1m", "5d", 1), "M5": ("5m", "60d", 1), "M15": ("15m", "60d", 1),
                    "M30": ("30m", "60d", 1), "H1": ("60m", "180d", 1), "H4": ("60m", "180d", 4),
                    "D1": ("1d", "2y", 1)}


def normalisieren(name):
    return name.upper().replace("/", "").replace(" ", "").replace(".CASH", "")


def yahoo_kuerzel(name):
    eintrag = SYMBOLE.get(normalisieren(name))
    return eintrag[0] if eintrag else None


def tradingview_kuerzel(name):
    n = normalisieren(name)
    if ":" in n:
        return n  # schon im Format BÖRSE:SYMBOL
    eintrag = SYMBOLE.get(n)
    return eintrag[1] if eintrag else None


def yahoo_auswerten(daten, buendeln=1):
    """Macht aus der Yahoo-Antwort eine Kerzenliste (Lücken ohne Kurs werden übersprungen)."""
    ergebnis = daten["chart"]["result"][0]
    zeiten = ergebnis.get("timestamp") or []
    q = ergebnis["indicators"]["quote"][0]
    kerzen = []
    for i, t in enumerate(zeiten):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        kerzen.append({"zeit": int(t), "open": float(o), "high": float(h), "low": float(l), "close": float(c)})
    if buendeln > 1:  # z. B. vier 1-Stunden-Kerzen zu einer 4-Stunden-Kerze
        gebuendelt = []
        for k in kerzen:
            block = k["zeit"] // (buendeln * 3600)
            if gebuendelt and gebuendelt[-1]["_block"] == block:
                g = gebuendelt[-1]
                g["high"], g["low"], g["close"] = max(g["high"], k["high"]), min(g["low"], k["low"]), k["close"]
            else:
                gebuendelt.append(dict(k, _block=block, zeit=block * buendeln * 3600))
        kerzen = [{k: v for k, v in g.items() if k != "_block"} for g in gebuendelt]
    return kerzen


def yahoo_kerzen(name, zeitrahmen="M15", anzahl=300):
    kuerzel = yahoo_kuerzel(name)
    if not kuerzel:
        raise ValueError(f"Für '{name}' kenne ich keine freie Kursquelle.")
    intervall, zeitraum, buendeln = YAHOO_ZEITRAHMEN[zeitrahmen.upper()]
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(kuerzel)}"
           f"?interval={intervall}&range={zeitraum}")
    anfrage = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(anfrage, timeout=20) as antwort:
        daten = json.loads(antwort.read())
    return kuerzel, yahoo_auswerten(daten, buendeln)[-anzahl:]
