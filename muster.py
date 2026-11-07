"""
Muster der Top-Trader: WIE handeln die besten Hyperliquid-Trader – und was davon bringt Geld?

Für jeden abgeschlossenen Trade (aus der Datenbank von main.py) wird festgehalten:
  - Uhrzeit und Wochentag des Einstiegs (österreichische Zeit)
  - Haltedauer
  - Long oder Short
  - Marktlage beim Einstieg (aus 1-Stunden-Kerzen des Coins):
      Trend:  mit dem Trend / gegen den Trend / Seitwärts   (EMA20 und EMA50 auf H1)
      Art:    Pullback (Einstieg nach Rücksetzer an die EMA20) / Ausbruch (neues 20-Stunden-Hoch/Tief) / sonstiges
Danach wird je Merkmal gezählt: Anzahl Trades, Trefferquote, Gewinn. So sieht man z. B.:
„Die Top-Trader verdienen vor allem mit Pullbacks im Trend während der US-Sitzung.“

WICHTIG (ehrlich):
  - Das ist Krypto (Hyperliquid), nicht Gold/Forex – Muster müssen erst im eigenen Backtest bestehen.
  - Wer gerade „Top“ ist, hatte oft auch Glück (Survivorship-Bias). Daher zählt nur, was bei VIELEN Tradern
    und vielen Trades auftaucht.
  - Es werden KEINE Trades kopiert. Das Ergebnis sind Ideen für eigene Regeln.

Aufruf:  python muster.py [--db daten/hyperliquid.db] [--ausgabe berichte/muster.md]
"""

import argparse
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import analyse
import config
import datenbank
import hyperliquid_api

try:
    from zoneinfo import ZoneInfo
    WIEN = ZoneInfo("Europe/Vienna")
except Exception:  # pragma: no cover
    WIEN = timezone.utc

STUNDE_MS = 3600 * 1000
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


# ---------- kleine Indikatoren (eigenständig, ohne Jarvis) ----------

def ema(werte, n):
    if len(werte) < n:
        return [None] * len(werte)
    k = 2 / (n + 1)
    aktuell = sum(werte[:n]) / n
    ergebnis = [None] * (n - 1) + [aktuell]
    for w in werte[n:]:
        aktuell = w * k + aktuell * (1 - k)
        ergebnis.append(aktuell)
    return ergebnis


def marktlage(kerzen, richtung):
    """
    kerzen: H1-Kerzen BIS VOR dem Einstieg (die letzte ist abgeschlossen), ältester zuerst.
    Gibt (trend, art) zurück – aus Sicht des Trades (Long/Short).
    """
    if len(kerzen) < 60:
        return "unbekannt", "unbekannt"
    schluss = [k["close"] for k in kerzen]
    e20, e50 = ema(schluss, 20), ema(schluss, 50)
    preis = schluss[-1]
    if e20[-1] > e50[-1] and e50[-1] > e50[-11] and preis > e50[-1]:
        markt = "auf"
    elif e20[-1] < e50[-1] and e50[-1] < e50[-11] and preis < e50[-1]:
        markt = "ab"
    else:
        markt = "seitwärts"
    long = richtung == "Long"
    if markt == "seitwärts":
        trend = "Seitwärts"
    else:
        trend = "mit dem Trend" if (markt == "auf") == long else "gegen den Trend"

    hoch20 = max(k["high"] for k in kerzen[-21:-1])
    tief20 = min(k["low"] for k in kerzen[-21:-1])
    spanne = (sum(k["high"] - k["low"] for k in kerzen[-14:]) / 14) or 1e-9
    if (long and preis > hoch20) or (not long and preis < tief20):
        art = "Ausbruch"
    elif abs(preis - e20[-1]) <= 0.5 * spanne and ((long and markt == "auf") or (not long and markt == "ab")):
        art = "Pullback"
    elif (long and preis < tief20 + 0.5 * spanne) or (not long and preis > hoch20 - 0.5 * spanne):
        art = "Umkehr (am Extrem)"
    else:
        art = "sonstiges"
    return trend, art


def haltedauer_text(ms):
    minuten = ms / 60000
    if minuten < 15:
        return "a) unter 15 Min (Scalping)"
    if minuten < 60:
        return "b) 15–60 Min"
    if minuten < 240:
        return "c) 1–4 Std (Daytrading)"
    if minuten < 1440:
        return "d) 4–24 Std"
    return "e) über 1 Tag (Swing)"


def sitzung(stunde):
    if 1 <= stunde < 9:
        return "a) Asien (01–09 Uhr)"
    if 9 <= stunde < 14:
        return "b) London (09–14 Uhr)"
    if 14 <= stunde < 18:
        return "c) London+New York (14–18 Uhr)"
    if 18 <= stunde < 22:
        return "d) New York (18–22 Uhr)"
    return "e) Nacht (22–01 Uhr)"


# ---------- Auswertung ----------

def merkmale(trade, kerzen_h1):
    """Alle Merkmale eines Trades. kerzen_h1: Kerzen des Coins (ältester zuerst) oder []."""
    start = datetime.fromtimestamp(trade["start"] / 1000, WIEN)
    vorher = [k for k in kerzen_h1 if k["zeit"] + STUNDE_MS <= trade["start"]][-250:]
    trend, art = marktlage(vorher, trade["richtung"])
    return {"Sitzung": sitzung(start.hour), "Wochentag": f"{start.weekday()}) {WOCHENTAGE[start.weekday()]}",
            "Haltedauer": haltedauer_text(trade["ende"] - trade["start"]), "Richtung": trade["richtung"],
            "Trend beim Einstieg": trend, "Art des Einstiegs": art,
            "Trend + Art": f"{trend} / {art}"}


def auswerten(trades_je_trader, kerzen_je_coin):
    """
    trades_je_trader: {wallet: [abgeschlossene, vollständige Trades]}
    Gibt {merkmal: {wert: {"trades", "gewinner", "pnl", "trader"}}} zurück.
    """
    tabelle = defaultdict(lambda: defaultdict(lambda: {"trades": 0, "gewinner": 0, "pnl": 0.0, "trader": set()}))
    for wallet, trades in trades_je_trader.items():
        for t in trades:
            for name, wert in merkmale(t, kerzen_je_coin.get(t["coin"], [])).items():
                z = tabelle[name][wert]
                z["trades"] += 1
                z["gewinner"] += t["pnl"] > 0
                z["pnl"] += t["pnl"]
                z["trader"].add(wallet)
    return tabelle


def erkenntnisse(tabelle, min_trades=20, min_trader=3):
    """Die klarsten Muster: genug Trades UND bei mehreren Tradern, sortiert nach Gewinn pro Trade."""
    gut, schlecht = [], []
    for name in ("Trend + Art", "Sitzung", "Haltedauer", "Trend beim Einstieg", "Art des Einstiegs"):
        for wert, z in tabelle.get(name, {}).items():
            if z["trades"] < min_trades or len(z["trader"]) < min_trader or "unbekannt" in wert:
                continue
            eintrag = (z["pnl"] / z["trades"], name, wert, z)
            (gut if z["pnl"] > 0 else schlecht).append(eintrag)
    return sorted(gut, reverse=True)[:5], sorted(schlecht)[:5]


def geld(x):
    return f"{x:+,.0f} $".replace(",", ".")


def bericht(tabelle, anzahl_trader, anzahl_trades, zeitraum):
    z = [f"# Muster der Top-Trader (Hyperliquid)", "",
         f"Stand {datetime.now(WIEN):%d.%m.%Y %H:%M} · {anzahl_trader} Trader · {anzahl_trades} abgeschlossene Trades · {zeitraum}",
         "", "> Ehrlich: Krypto ≠ Gold/Forex, und wer gerade oben steht, hatte oft auch Glück. Diese Muster sind",
         "> **Ideen für eigene Regeln** – sie zählen erst, wenn sie im eigenen 2-Jahres-Backtest bestehen. "
         "Es werden keine Trades kopiert.", ""]
    gut, schlecht = erkenntnisse(tabelle)
    z.append("## Was bei den Profis Geld bringt")
    z += [f"- **{wert}** ({name}): {d['trades']} Trades von {len(d['trader'])} Tradern, Treffer "
          f"{d['gewinner'] / d['trades'] * 100:.0f} %, im Schnitt {geld(pro)} pro Trade" for pro, name, wert, d in gut] \
        or ["- Noch zu wenig Daten für klare Muster (mind. 20 Trades bei mind. 3 Tradern je Muster)."]
    z += ["", "## Was auch bei den Profis Geld kostet"]
    z += [f"- **{wert}** ({name}): {d['trades']} Trades, Treffer {d['gewinner'] / d['trades'] * 100:.0f} %, "
          f"im Schnitt {geld(pro)} pro Trade" for pro, name, wert, d in schlecht] or ["- nichts Auffälliges"]
    for name in ("Trend beim Einstieg", "Art des Einstiegs", "Sitzung", "Haltedauer", "Richtung", "Wochentag"):
        z += ["", f"## {name}", "", "| | Trades | Trader | Treffer | Gewinn gesamt | pro Trade |", "|---|---:|---:|---:|---:|---:|"]
        for wert, d in sorted(tabelle.get(name, {}).items()):
            z.append(f"| {wert} | {d['trades']} | {len(d['trader'])} | {d['gewinner'] / d['trades'] * 100:.0f} % | "
                     f"{geld(d['pnl'])} | {geld(d['pnl'] / d['trades'])} |")
    return "\n".join(z) + "\n"


# ---------- Daten holen ----------

def kerzen_laden(coin, von_ms, bis_ms):
    """H1-Kerzen von Hyperliquid (höchstens 5000 pro Anfrage)."""
    ergebnis = []
    start = von_ms
    while start < bis_ms:
        ende = min(bis_ms, start + 4900 * STUNDE_MS)
        daten = hyperliquid_api._anfrage(hyperliquid_api.INFO_URL, {"type": "candleSnapshot", "req": {
            "coin": coin, "interval": "1h", "startTime": start, "endTime": ende}})
        ergebnis += [{"zeit": int(k["t"]), "open": float(k["o"]), "high": float(k["h"]),
                      "low": float(k["l"]), "close": float(k["c"])} for k in daten or []]
        start = ende
    return sorted({k["zeit"]: k for k in ergebnis}.values(), key=lambda k: k["zeit"])


def main():
    parser = argparse.ArgumentParser(description="Muster der Top-Trader auswerten")
    parser.add_argument("--db", default=str(config.DATENBANK_DATEI))
    parser.add_argument("--ausgabe", default="berichte/muster.md")
    parser.add_argument("--max-coins", type=int, default=15, help="Kerzen nur für die meistgehandelten Coins laden")
    a = parser.parse_args()

    db = datenbank.verbinden(a.db)
    trades_je_trader = {}
    for t in datenbank.top_trader(db):
        trades, _ = analyse.baue_trades(datenbank.fills_von(db, t["wallet"]))
        trades_je_trader[t["wallet"]] = [x for x in trades if x["vollstaendig"] and x["ende"]]
    alle = [t for liste in trades_je_trader.values() for t in liste]
    print(f"{len(trades_je_trader)} Trader, {len(alle)} abgeschlossene Trades")
    if not alle:
        Path(a.ausgabe).parent.mkdir(parents=True, exist_ok=True)
        Path(a.ausgabe).write_text("# Muster der Top-Trader\n\nNoch keine abgeschlossenen Trades in der Datenbank.\n",
                                   encoding="utf-8")
        return

    haeufigkeit = defaultdict(int)
    for t in alle:
        haeufigkeit[t["coin"]] += 1
    coins = sorted(haeufigkeit, key=haeufigkeit.get, reverse=True)[:a.max_coins]
    von = min(t["start"] for t in alle) - 260 * STUNDE_MS
    bis = int(time.time() * 1000)
    kerzen = {}
    for coin in coins:
        try:
            kerzen[coin] = kerzen_laden(coin, von, bis)
            print(f"  {coin}: {len(kerzen[coin])} H1-Kerzen")
        except Exception as fehler:
            print(f"  {coin}: keine Kerzen ({fehler})")
    tabelle = auswerten(trades_je_trader, kerzen)
    zeitraum = (f"{datetime.fromtimestamp(min(t['start'] for t in alle) / 1000, WIEN):%d.%m.%Y} bis "
                f"{datetime.fromtimestamp(max(t['ende'] for t in alle) / 1000, WIEN):%d.%m.%Y}")
    text = bericht(tabelle, len(trades_je_trader), len(alle), zeitraum)
    Path(a.ausgabe).parent.mkdir(parents=True, exist_ok=True)
    Path(a.ausgabe).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
