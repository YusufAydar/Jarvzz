"""
Liefert die Daten für den Trading Desk (Chart, Konto, Marktüberblick).

Kursquelle: MetaTrader 5. Ist MT5 nicht erreichbar, kommen Krypto-Kurse
(BTC, ETH, SOL, ...) ersatzweise von Hyperliquid – so funktioniert der Chart trotzdem.
"""

import json
import threading
import time
import urllib.request

import einstellungen
from trading import indikatoren as ind
from trading import kursquellen
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


def _stellen_schaetzen(preis):
    return 2 if preis >= 100 else 3 if preis >= 10 else 5


# Zwischenspeicher für Internet-Kursquellen (MT5 ist lokal und schnell, das wird nie gespeichert).
# So holen Chart, Watchlist, Setup-Scanner und Alarme die Kerzen nicht alle einzeln aus dem Internet.
_CACHE_SEKUNDEN = {"M1": 15, "M5": 20, "M15": 30, "M30": 45, "H1": 90, "H4": 300, "D1": 900}
_cache = {}
_cache_sperre = threading.Lock()


def _aus_cache(schluessel, sekunden, laden):
    with _cache_sperre:
        eintrag = _cache.get(schluessel)
        if eintrag and time.time() - eintrag[0] < sekunden:
            return eintrag[1]
    wert = laden()
    with _cache_sperre:
        _cache[schluessel] = (time.time(), wert)
    return wert


def kerzen_holen(symbol, zeitrahmen, anzahl=300):
    """
    Gibt (symbolname, nachkommastellen, quelle, kerzen) zurück.
    Reihenfolge: MetaTrader 5 -> Hyperliquid (Krypto) -> Yahoo Finance (Gold, Forex, Indizes).
    """
    zeitrahmen = zeitrahmen.upper()
    try:
        sym, kerzen = mt.kerzen(symbol, zeitrahmen, anzahl)
        return sym, mt.nachkommastellen(sym), "MT5", kerzen
    except mt.MT5Fehler as fehler:
        mt5_fehler = fehler
    menge = max(anzahl, 400)
    sekunden = _CACHE_SEKUNDEN.get(zeitrahmen, 30)
    coin = KRYPTO.get(symbol.upper().replace("/", ""))
    if coin:
        try:
            kerzen = _aus_cache(("HL", coin, zeitrahmen, menge), sekunden,
                                lambda: _hyperliquid_kerzen(coin, zeitrahmen, menge))
            if kerzen:
                return (f"{coin} (Hyperliquid)", _stellen_schaetzen(kerzen[-1]["close"]), "Hyperliquid",
                        kerzen[-anzahl:])
        except Exception:
            pass
    internet_fehler = None
    if kursquellen.yahoo_kuerzel(symbol):
        try:
            kuerzel, kerzen = _aus_cache(("Y", kursquellen.yahoo_kuerzel(symbol), zeitrahmen, menge), sekunden,
                                         lambda: kursquellen.yahoo_kerzen(symbol, zeitrahmen, menge))
            if kerzen:
                return (f"{symbol.upper()} ({kuerzel})", _stellen_schaetzen(kerzen[-1]["close"]),
                        "Yahoo Finance", kerzen[-anzahl:])
        except Exception as fehler:
            internet_fehler = fehler
    if coin or internet_fehler:
        raise mt.MT5Fehler(f"Keine Kurse: Internet-Kursquelle nicht erreichbar, MT5 auch nicht ({mt5_fehler})")
    raise mt.MT5Fehler(f"Für {symbol} gibt es nur Kurse über MT5 ({mt5_fehler})")


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
            try:
                trend_h1 = ind.trend(kerzen_holen(name, "H1", 200)[3])
            except Exception:
                trend_h1 = None
            ergebnis.append({"name": name, "symbol": sym, "preis": schluss[-1], "stellen": stellen,
                             "quelle": quelle, "trend": ind.trend(kerzen), "trend_h1": trend_h1,
                             "rsi": ind.rsi(schluss)[-1],
                             "prozent": (schluss[-1] / tag_start - 1) * 100 if tag_start else 0})
        except Exception as fehler:
            ergebnis.append({"name": name, "fehler": str(fehler)[:120]})
    return ergebnis


def setups_daten(zeitrahmen="M15", maerkte=None):
    """Setup-Scanner für alle Märkte – als Daten für die Zentrale."""
    from trading import setups
    ergebnis = []
    for name in maerkte or einstellungen.TRADING_MAERKTE:
        try:
            sym, stellen, quelle, kerzen = kerzen_holen(name, zeitrahmen, 300)
            h1 = kerzen_holen(name, "H1", 200)[3]
        except Exception as fehler:
            ergebnis.append({"name": name, "fehler": str(fehler)[:120]})
            continue
        e = setups.finde_setup(kerzen, h1, name, stellen)
        ergebnis.append({"name": name, "stellen": stellen, "quelle": quelle, "setup": e.get("setup"),
                         "grund": e.get("grund"), "trend_h1": e.get("trend_h1"), "rsi": e.get("rsi"),
                         "preis": e.get("preis")})
    return ergebnis


def positions_rechner(symbol, einstieg, stop, risiko_prozent=None):
    """Lotgröße für festes Risiko. Nutzt MT5-Kontraktdaten und -Kontostand, wenn verfügbar."""
    from trading import setups
    risiko_prozent = einstellungen.RISIKO_STANDARD_PROZENT if risiko_prozent is None else risiko_prozent
    wert = None
    schritt = 0.01
    konto = einstellungen.FTMO_KONTOGROESSE
    konto_quelle = "Kontogröße aus den Einstellungen"
    try:
        wert, schritt = mt.kontrakt_info(symbol)
        konto = mt.kontostand()["equity"]
        konto_quelle = "Equity aus MT5"
    except Exception:
        pass
    r = setups.positionsgroesse(konto, risiko_prozent, einstieg, stop, wert, schritt or 0.01, symbol)
    r.update({"konto": konto, "konto_quelle": konto_quelle, "risiko_prozent": risiko_prozent})
    return r
