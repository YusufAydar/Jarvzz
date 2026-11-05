"""
TradingView-Analyse: die "Technical Ratings" von TradingView (Kaufen/Verkaufen-Zusammenfassung
aus 26 Indikatoren: gleitende Durchschnitte + Oszillatoren) für mehrere Zeitrahmen.

Quelle ist der öffentliche TradingView-Screener (ohne Konto). Das ist keine offizielle
Schnittstelle – wenn TradingView etwas ändert, kann sie ausfallen; dann sagt Jarvis das.
"""

import json
import urllib.request

ZEITRAHMEN = {"M5": "5", "M15": "15", "H1": "60", "H4": "240", "D1": ""}
SPALTEN = ["Recommend.All", "Recommend.MA", "Recommend.Other", "RSI", "MACD.macd", "MACD.signal",
           "Stoch.K", "ADX", "ATR", "EMA20", "EMA50", "EMA200", "close"]
TAGES_SPALTEN = ["change", "Pivot.M.Classic.S1", "Pivot.M.Classic.Middle", "Pivot.M.Classic.R1"]


def bewertung(wert):
    """TradingView-Skala -1..+1 in Worte."""
    if wert is None:
        return "keine Daten"
    if wert >= 0.5:
        return "STARK KAUFEN"
    if wert >= 0.1:
        return "KAUFEN"
    if wert > -0.1:
        return "NEUTRAL"
    if wert > -0.5:
        return "VERKAUFEN"
    return "STARK VERKAUFEN"


def spalten_fuer(zeitrahmen):
    spalten = []
    for tf in zeitrahmen:
        suffix = ZEITRAHMEN[tf]
        spalten += [s + (f"|{suffix}" if suffix else "") for s in SPALTEN]
    return spalten + TAGES_SPALTEN


def anfrage_body(ticker, zeitrahmen):
    return {"symbols": {"tickers": [ticker], "query": {"types": []}}, "columns": spalten_fuer(zeitrahmen)}


def auswerten(antwort, zeitrahmen):
    """Ordnet die Werte aus der Screener-Antwort den Zeitrahmen zu."""
    zeilen = antwort.get("data") or []
    if not zeilen:
        return None
    werte = dict(zip(spalten_fuer(zeitrahmen), zeilen[0]["d"]))
    ergebnis = {"ticker": zeilen[0]["s"], "zeitrahmen": {}}
    for tf in zeitrahmen:
        suffix = ZEITRAHMEN[tf]
        w = {s: werte.get(s + (f"|{suffix}" if suffix else "")) for s in SPALTEN}
        ergebnis["zeitrahmen"][tf] = w
    ergebnis["tag"] = {s: werte.get(s) for s in TAGES_SPALTEN}
    return ergebnis


def analyse(ticker, zeitrahmen=("M15", "H1", "H4", "D1")):
    anfrage = urllib.request.Request(
        "https://scanner.tradingview.com/global/scan",
        data=json.dumps(anfrage_body(ticker, zeitrahmen)).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(anfrage, timeout=20) as antwort:
        return auswerten(json.loads(antwort.read()), zeitrahmen)


def zusammenfassung(name, e):
    if e is None:
        return f"TradingView kennt '{name}' nicht."
    f = lambda x, n=2: "–" if x is None else f"{x:.{n}f}"
    zeilen = [f"TradingView-Analyse {e['ticker']}"]
    for tf, w in e["zeitrahmen"].items():
        zeilen.append(
            f"{tf}: GESAMT {bewertung(w['Recommend.All'])} (MA {bewertung(w['Recommend.MA'])}, "
            f"Oszillatoren {bewertung(w['Recommend.Other'])}) | RSI {f(w['RSI'], 1)} | "
            f"MACD {'über' if (w['MACD.macd'] or 0) > (w['MACD.signal'] or 0) else 'unter'} Signal | "
            f"ADX {f(w['ADX'], 0)} | ATR {f(w['ATR'], 4)}")
    t = e["tag"]
    zeilen.append(f"Kurs {f(e['zeitrahmen'][next(iter(e['zeitrahmen']))]['close'], 4)}, "
                  f"heute {f(t['change'])} % | Monats-Pivots S1 {f(t['Pivot.M.Classic.S1'], 4)}, "
                  f"P {f(t['Pivot.M.Classic.Middle'], 4)}, R1 {f(t['Pivot.M.Classic.R1'], 4)}")
    stimmen = [bewertung(w["Recommend.All"]) for w in e["zeitrahmen"].values()]
    # Achtung: "VERKAUFEN" enthält das Wort "KAUFEN" – deshalb zuerst auf VERKAUFEN prüfen
    if all("VERKAUFEN" not in s and "KAUFEN" in s for s in stimmen):
        zeilen.append("Alle Zeitrahmen zeigen KAUFEN – klare Richtung nach oben.")
    elif all("VERKAUFEN" in s for s in stimmen):
        zeilen.append("Alle Zeitrahmen zeigen VERKAUFEN – klare Richtung nach unten.")
    else:
        zeilen.append("Die Zeitrahmen sind sich nicht einig – Vorsicht, eher abwarten oder kleiner handeln.")
    return "\n".join(zeilen)
