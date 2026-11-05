import json
import urllib.request

WERKZEUG = {
    "name": "tradingview_markt",
    "description": "Marktdaten direkt von TradingView (statt MetaTrader): Kurs, Tagesänderung, RSI, EMA20/50, ATR, MACD und TradingView-Empfehlung (Kaufen/Verkaufen) auf einem Zeitrahmen. Ohne Symbol: Überblick über die Standard-Märkte (EURUSD, Gold, US30, US100, DAX, BTC, ETH, Öl). Symbole frei, z. B. 'Gold', 'EURUSD', 'BINANCE:SOLUSDT'.",
    "input_schema": {
        "type": "object",
        "properties": {
            "symbole": {"type": "string", "description": "Kommagetrennt, z. B. 'Gold, DAX'. Leer = Standard-Überblick."},
            "zeitrahmen": {"type": "string", "enum": ["1", "5", "15", "30", "60", "240", "1D"], "description": "Minuten oder 1D. Standard 15."}
        }
    }
}

ALIASE = {
    "EURUSD": "FX:EURUSD", "GBPUSD": "FX:GBPUSD", "USDJPY": "FX:USDJPY",
    "GOLD": "OANDA:XAUUSD", "XAUUSD": "OANDA:XAUUSD", "SILBER": "OANDA:XAGUSD",
    "US30": "OANDA:US30USD", "DOW": "OANDA:US30USD",
    "US100": "OANDA:NAS100USD", "NASDAQ": "OANDA:NAS100USD",
    "US500": "OANDA:SPX500USD", "SP500": "OANDA:SPX500USD",
    "DAX": "OANDA:DE30EUR", "GER40": "OANDA:DE30EUR",
    "BTC": "BINANCE:BTCUSDT", "BTCUSD": "BINANCE:BTCUSDT", "BITCOIN": "BINANCE:BTCUSDT",
    "ETH": "BINANCE:ETHUSDT", "ETHUSD": "BINANCE:ETHUSDT",
    "OEL": "OANDA:WTICOUSD", "ÖL": "OANDA:WTICOUSD", "WTI": "OANDA:WTICOUSD",
}
STANDARD = ["EURUSD", "GOLD", "US30", "US100", "DAX", "BTC", "ETH", "OEL"]


def _empfehlung(w):
    if w is None:
        return "unbekannt"
    if w >= 0.5: return "starkes Kaufen"
    if w >= 0.1: return "Kaufen"
    if w > -0.1: return "neutral"
    if w > -0.5: return "Verkaufen"
    return "starkes Verkaufen"


def _r(x, n=2):
    return "?" if x is None else str(round(x, n)).replace(".", ",")


def ausfuehren(symbole="", zeitrahmen="15"):
    tf = zeitrahmen or "15"
    suf = "" if tf == "1D" else "|" + tf
    namen = [s.strip() for s in (symbole or "").split(",") if s.strip()] or STANDARD
    ticker = [ALIASE.get(n.upper(), n.upper()) for n in namen]
    spalten = ["close" + suf, "change", "RSI" + suf, "EMA20" + suf, "EMA50" + suf,
               "ATR" + suf, "MACD.macd" + suf, "MACD.signal" + suf, "Recommend.All" + suf]
    body = json.dumps({"symbols": {"tickers": ticker, "query": {"types": []}}, "columns": spalten}).encode()
    req = urllib.request.Request("https://scanner.tradingview.com/global/scan", data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            daten = json.loads(r.read().decode()).get("data", [])
    except Exception as e:
        return "TradingView nicht erreichbar: " + str(e)
    if not daten:
        return "Keine Daten von TradingView für: " + ", ".join(ticker)
    zeilen = ["TradingView, Zeitrahmen " + tf + ":"]
    for d in daten:
        c, chg, rsi, e20, e50, atr, macd, sig, rec = d["d"]
        trend = "?"
        if c and e20 and e50:
            trend = "aufwärts" if c > e20 > e50 else "abwärts" if c < e20 < e50 else "seitwärts"
        macd_t = "?" if macd is None or sig is None else ("bullisch" if macd > sig else "bärisch")
        zeilen.append(f"{d['s']}: Kurs {_r(c, 5)}, Tag {_r(chg)} %, Trend {trend}, RSI {_r(rsi, 1)}, "
                      f"EMA20 {_r(e20, 5)}, EMA50 {_r(e50, 5)}, ATR {_r(atr, 5)}, MACD {macd_t}, "
                      f"Empfehlung {_empfehlung(rec)}")
    return "\n".join(zeilen)
