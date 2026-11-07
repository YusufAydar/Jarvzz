"""
Prüft die echten Datenquellen von Jarvis' Trading-Werkzeugen (läuft in GitHub Actions).
Gibt pro Quelle eine Zeile aus und endet mit Fehlercode, wenn eine Quelle nicht funktioniert.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jarvis"))

from trading import indikatoren, kalender, kursquellen, marktdaten, setups, tradingview  # noqa: E402

fehler = 0


def pruefe(name, funktion):
    global fehler
    try:
        print(f"OK   {name}: {funktion()}")
    except Exception:
        fehler += 1
        print(f"FEHL {name}:\n{traceback.format_exc()}")


def yahoo(symbol, tf):
    kuerzel, k = kursquellen.yahoo_kerzen(symbol, tf, 300)
    assert len(k) >= 60, f"nur {len(k)} Kerzen"
    return f"{kuerzel} {tf}: {len(k)} Kerzen, letzter Kurs {k[-1]['close']:.4f}, Trend {indikatoren.trend(k)}"


def tv(symbol):
    e = tradingview.analyse(kursquellen.tradingview_kuerzel(symbol))
    assert e and e["zeitrahmen"]["H1"]["Recommend.All"] is not None, "keine Werte"
    return tradingview.zusammenfassung(symbol, e).replace("\n", " || ")


def hl():
    sym, stellen, quelle, k = marktdaten.kerzen_holen("BTCUSD", "M15", 200)
    assert quelle == "Hyperliquid" and len(k) > 100
    return f"{sym}: {len(k)} Kerzen, {k[-1]['close']:.{stellen}f}"


def scanner():
    zeilen = []
    for name in ("XAUUSD", "EURUSD", "US30", "BTCUSD"):
        _, stellen, quelle, k = marktdaten.kerzen_holen(name, "M15", 300)
        h1 = marktdaten.kerzen_holen(name, "H1", 200)[3]
        zeilen.append(setups.setup_text(setups.finde_setup(k, h1, name, stellen), stellen) + f" [{quelle}]")
    return " || ".join(zeilen)


def news():
    daten = kalender.laden()
    assert isinstance(daten, list) and daten, "leerer Kalender"
    return f"{len(daten)} Termine diese Woche, z. B. {daten[0].get('title')} ({daten[0].get('country')})"


pruefe("Yahoo Gold M15", lambda: yahoo("XAUUSD", "M15"))
pruefe("Yahoo DAX H4", lambda: yahoo("DAX", "H4"))
pruefe("Yahoo EURUSD D1", lambda: yahoo("EURUSD", "D1"))
pruefe("TradingView Gold", lambda: tv("XAUUSD"))
pruefe("TradingView US30", lambda: tv("US30"))
pruefe("TradingView BTC", lambda: tv("BTCUSD"))
pruefe("Hyperliquid BTC", hl)
pruefe("Setup-Scanner", scanner)
pruefe("Wirtschaftskalender", news)


def dukascopy():
    from trading import historie
    kerzen = historie.m15_laden("EURUSD", 7)
    assert len(kerzen) > 100, f"nur {len(kerzen)} Kerzen"
    return f"EURUSD: {len(kerzen)} M15-Kerzen aus 7 Tagen, letzter Kurs {kerzen[-1]['close']:.5f}"


def dukascopy_h1():
    import tempfile
    from trading import historie
    with tempfile.TemporaryDirectory() as ordner:
        info = {}
        kerzen = historie.h1_laden("XAUUSD", 1, ordner=ordner, info=info)
    assert len(kerzen) > 4000, f"nur {len(kerzen)} Stundenkerzen in einem Jahr"
    assert 300 < kerzen[-1]["close"] < 20000, f"Goldpreis unplausibel: {kerzen[-1]['close']}"
    return f"Gold: {len(kerzen)} H1-Kerzen aus 1 Jahr (ab {info['beginn']}), letzter Kurs {kerzen[-1]['close']:.2f}"


pruefe("Dukascopy-Historie", dukascopy)
pruefe("Dukascopy-Stundenkerzen (Langzeit)", dukascopy_h1)
print(f"\n{fehler} Fehler")
sys.exit(1 if fehler else 0)
