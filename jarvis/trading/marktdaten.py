"""
Liefert die Daten für den Trading Desk (Chart, Konto, Marktüberblick).

Kursquelle: MetaTrader 5. Ist MT5 nicht erreichbar, kommen Krypto-Kurse
(BTC, ETH, SOL, ...) ersatzweise von Hyperliquid – so funktioniert der Chart trotzdem.
"""

import json
import time
import urllib.request

import einstellungen
from trading import indikatoren as ind
from trading import mt5_verbindung as mt

HL_INTERVALLE = {"M1": ("1m", 60), "M5": ("5m", 300), "M15": ("15m", 900), "M30": ("30m", 1800),
                 "H1": ("1h", 3600), "H4": ("4h", 14400), "D1": ("1d", 86400)}
KRYPTO = {"BTCUSD": "BTC", "BTC": "BTC", "BITCOIN": "BTC", "ETHUSD": "ETH", "ETH": "ETH", "ETHEREUM": "ETH",
          "SOLUSD": "SOL", "SOL": "SOL", "HYPE": "HYPE", "XRPUSD": "XRP", "XRP": "XRP"}


def _hyperliquid_kerzen(coin, zeitrahmen, anzahl):
    intervall, sekunden = HL_INTERVALLE[zeitrahmen]
    ende = int(time.time() * 1000)
    anfrage = urllib.request.Request(
        "https://api.hyperliquid.xyz/info",
        data=json.dumps({"type": "candleSnapshot", "req": {
            "coin": coin, "interval": intervall,
            "startTime": ende - anzahl * sekunden * 1000, "endTime": ende}}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "jarvis"})
    with urllib.request.urlopen(anfrage, timeout=15) as antwort:
        daten = json.loads(antwort.read())
    return [{"zeit": int(k["t"]) // 1000, "open": float(k["o"]), "high": float(k["h"]),
             "low": float(k["l"]), "close": float(k["c"])} for k in daten]


def kerzen_holen(symbol, zeitrahmen, anzahl=300):
    """Gibt (symbolname, nachkommastellen, quelle, kerzen) zurück."""
    try:
        sym, kerzen = mt.kerzen(symbol, zeitrahmen, anzahl)
        return sym, mt.nachkommastellen(sym), "MT5", kerzen
    except mt.MT5Fehler as mt5_fehler:
        coin = KRYPTO.get(symbol.upper().replace("/", ""))
        if not coin:
            raise
        try:
            kerzen = _hyperliquid_kerzen(coin, zeitrahmen, anzahl)
        except Exception:
            raise mt5_fehler
        stellen = 2 if kerzen and kerzen[-1]["close"] > 100 else 4
        return f"{coin} (Hyperliquid)", stellen, "Hyperliquid", kerzen


def chart_daten(symbol, zeitrahmen):
    """Alles, was der Chart braucht: Kerzen, EMAs, Zonen, Pivots und die Analyse."""
    zeitrahmen = zeitrahmen.upper()
    sym, stellen, quelle, kerzen = kerzen_holen(symbol, zeitrahmen, 400)
    if len(kerzen) < 60:
        raise mt.MT5Fehler(f"Zu wenig Kursdaten für {sym}.")
    h1 = None
    if zeitrahmen != "H1":
        try:
            h1 = kerzen_holen(symbol, "H1", 200)[3]
        except Exception:
            pass
    vortag = None
    try:
        tage = kerzen_holen(symbol, "D1", 3)[3]
        vortag = tage[-2] if len(tage) >= 2 else None
    except Exception:
        pass
    a = ind.analysiere(kerzen, h1, vortag)
    schluss = [k["close"] for k in kerzen]
    e20, e50 = ind.ema(schluss, 20), ind.ema(schluss, 50)
    linie = lambda werte: [{"time": k["zeit"], "value": round(w, stellen + 2)}
                           for k, w in zip(kerzen, werte) if w is not None]
    rsi = ind.rsi(schluss)
    return {
        "symbol": sym, "quelle": quelle, "zeitrahmen": zeitrahmen, "stellen": stellen,
        "kerzen": [{"time": k["zeit"], "open": k["open"], "high": k["high"], "low": k["low"],
                    "close": k["close"]} for k in kerzen],
        "ema20": linie(e20), "ema50": linie(e50), "rsi": linie(rsi),
        "analyse": {
            "preis": a["preis"], "trend": a["trend"], "trend_h1": a["trend_h1"],
            "rsi": a["rsi"], "macd_hist": a["macd_hist"], "macd_kreuzung": a["macd_kreuzung"],
            "atr": a["atr"], "unterstuetzungen": a["unterstuetzungen"],
            "widerstaende": a["widerstaende"], "pivots": a["pivots"],
        },
    }


def konto_daten():
    konto = mt.kontostand()
    start = mt.tagesstart_balance(konto["balance"])
    pruefung = mt.ftmo_pruefung(konto, start, einstellungen.FTMO_KONTOGROESSE)
    return {"konto": konto, "pruefung": pruefung, "tagesstart": start,
            "regeln": {"kontogroesse": einstellungen.FTMO_KONTOGROESSE,
                       "max_tag": einstellungen.FTMO_MAX_TAGESVERLUST,
                       "max_gesamt": einstellungen.FTMO_MAX_GESAMTVERLUST,
                       "ziel": einstellungen.FTMO_GEWINNZIEL,
                       "sicher_tag": einstellungen.SICHERHEIT_TAGESVERLUST}}


def ueberblick_daten():
    ergebnis = []
    for name in einstellungen.TRADING_MAERKTE:
        try:
            sym, stellen, quelle, kerzen = kerzen_holen(name, einstellungen.TRADING_ZEITRAHMEN, 200)
            schluss = [k["close"] for k in kerzen]
            tag_start = next((k["open"] for k in kerzen if time.gmtime(k["zeit"]).tm_yday
                              == time.gmtime(kerzen[-1]["zeit"]).tm_yday), kerzen[0]["open"])
            ergebnis.append({"name": name, "symbol": sym, "preis": schluss[-1], "stellen": stellen,
                             "trend": ind.trend(kerzen), "rsi": ind.rsi(schluss)[-1],
                             "prozent": (schluss[-1] / tag_start - 1) * 100 if tag_start else 0})
        except Exception as fehler:
            ergebnis.append({"name": name, "fehler": str(fehler)[:120]})
    return ergebnis
