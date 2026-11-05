"""
Setup-Scanner und Risiko-Rechner für Daytrading.

Die Regeln sind bewusst einfach und fest – damit sie nachvollziehbar und testbar sind:

LONG-Setup ("Pullback im Aufwärtstrend"):
  1. H1 ist im Aufwärtstrend (übergeordnete Richtung)
  2. Auf dem Einstiegs-Zeitrahmen ist der Kurs zurückgekommen: höchstens 0,6 ATR von
     EMA20/EMA50 oder einer Unterstützung entfernt
  3. RSI zwischen 35 und 65 und steigt wieder (Schwung dreht nach oben)
  4. MACD-Histogramm steigt
  Stop-Loss: unter dem letzten Tief der letzten 10 Kerzen bzw. mindestens 1 ATR, höchstens 2,5 ATR
  Ziel: 2-faches Risiko (CRV 2), es sei denn, ein Widerstand liegt näher (dann nur, wenn CRV ≥ 1,5)
SHORT-Setup: genau gespiegelt.

Das ist KEIN Gewinn-Versprechen – es ist ein Filter, der dir Kandidaten zeigt.
"""

from trading import indikatoren as ind


def finde_setup(kerzen, kerzen_h1, name="?", stellen=5):
    """Gibt ein Setup-dict zurück oder None (mit Grund im Feld 'grund')."""
    if len(kerzen) < 60 or not kerzen_h1 or len(kerzen_h1) < 60:
        return {"name": name, "setup": None, "grund": "zu wenig Daten"}
    schluss = [k["close"] for k in kerzen]
    e20, e50 = ind.ema(schluss, 20), ind.ema(schluss, 50)
    rsi = ind.rsi(schluss)
    _, _, hist = ind.macd(schluss)
    atr = ind.atr(kerzen)[-1]
    trend_h1 = ind.trend(kerzen_h1)
    unter, ueber = ind.preiszonen(kerzen[-150:], atr_wert=atr)
    preis = schluss[-1]
    if not atr:
        return {"name": name, "setup": None, "grund": "keine Schwankung messbar"}

    def nah(level):
        return level is not None and abs(preis - level) <= 0.6 * atr

    ergebnis = {"name": name, "preis": preis, "trend_h1": trend_h1, "rsi": rsi[-1], "atr": atr, "setup": None}
    if trend_h1 == "Aufwärtstrend":
        richtung = "LONG"
        pullback = nah(e20[-1]) or nah(e50[-1]) or any(nah(p) for p, _ in unter[:1])
        schwung = 35 <= rsi[-1] <= 65 and rsi[-1] > rsi[-2] and hist[-1] > hist[-2]
        tief = min(k["low"] for k in kerzen[-10:])
        stop = preis - min(max(preis - tief + 0.2 * atr, 1.0 * atr), 2.5 * atr)
        ziel_zone = ueber[0][0] if ueber else None
    elif trend_h1 == "Abwärtstrend":
        richtung = "SHORT"
        pullback = nah(e20[-1]) or nah(e50[-1]) or any(nah(p) for p, _ in ueber[:1])
        schwung = 35 <= rsi[-1] <= 65 and rsi[-1] < rsi[-2] and hist[-1] < hist[-2]
        hoch = max(k["high"] for k in kerzen[-10:])
        stop = preis + min(max(hoch - preis + 0.2 * atr, 1.0 * atr), 2.5 * atr)
        ziel_zone = unter[0][0] if unter else None
    else:
        ergebnis["grund"] = f"H1 {trend_h1} – kein klarer Trend"
        return ergebnis

    if not pullback:
        ergebnis["grund"] = f"{richtung}-Trend, aber Kurs ist nicht an EMA/Zone zurückgekommen (Einstieg wäre hinterherrennen)"
        return ergebnis
    if not schwung:
        ergebnis["grund"] = f"{richtung}-Trend und Pullback da, aber RSI/MACD drehen noch nicht"
        return ergebnis

    risiko = abs(preis - stop)
    ziel = preis + 2 * risiko if richtung == "LONG" else preis - 2 * risiko
    if ziel_zone is not None:
        abstand_zone = abs(ziel_zone - preis)
        if abstand_zone < 2 * risiko:
            if abstand_zone < 1.5 * risiko:
                ergebnis["grund"] = f"{richtung}-Setup, aber die nächste Zone ({ziel_zone:.{stellen}f}) ist zu nah (CRV < 1,5)"
                return ergebnis
            ziel = ziel_zone
    ergebnis["setup"] = {"richtung": richtung, "einstieg": preis, "stop": stop, "ziel": ziel,
                         "crv": abs(ziel - preis) / risiko, "risiko_punkte": risiko}
    return ergebnis


def setup_text(e, stellen=5):
    f = lambda x: f"{x:.{stellen}f}"
    if not e.get("setup"):
        return f"{e['name']}: kein Setup – {e.get('grund', '')}"
    s = e["setup"]
    return (f"{e['name']}: {s['richtung']}-SETUP | Einstieg {f(s['einstieg'])} | Stop-Loss {f(s['stop'])} | "
            f"Ziel {f(s['ziel'])} | CRV {s['crv']:.1f} | H1 {e['trend_h1']}, RSI {e['rsi']:.0f}")


# Standard-Kontraktgrößen (nur wenn MT5 keine genauen Daten liefert). Beim Broker prüfen!
STANDARD_KONTRAKTE = {"XAUUSD": 100, "XAGUSD": 5000, "EURUSD": 100000, "GBPUSD": 100000,
                      "AUDUSD": 100000, "NZDUSD": 100000}


def positionsgroesse(kontogroesse, risiko_prozent, einstieg, stop, wert_pro_punkt_und_lot=None,
                     lot_schritt=0.01, symbol=None):
    """
    Wie groß darf die Position sein, damit beim Stop-Loss genau risiko_prozent verloren gehen?
    wert_pro_punkt_und_lot: wie viel Kontowährung 1,0 Preisbewegung bei 1 Lot bringt.
    """
    risiko_betrag = kontogroesse * risiko_prozent / 100
    abstand = abs(einstieg - stop)
    if abstand <= 0:
        raise ValueError("Einstieg und Stop-Loss dürfen nicht gleich sein.")
    quelle = "MT5"
    if wert_pro_punkt_und_lot is None:
        wert_pro_punkt_und_lot = STANDARD_KONTRAKTE.get((symbol or "").upper())
        quelle = "Standard-Kontraktgröße (beim Broker prüfen!)"
    if not wert_pro_punkt_und_lot:
        return {"risiko_betrag": risiko_betrag, "abstand": abstand, "lots": None, "quelle": None}
    roh = risiko_betrag / (abstand * wert_pro_punkt_und_lot)
    lots = int(roh / lot_schritt) * lot_schritt  # abrunden, nie mehr Risiko als erlaubt
    return {"risiko_betrag": risiko_betrag, "abstand": abstand, "lots": round(lots, 2),
            "tatsaechliches_risiko": lots * abstand * wert_pro_punkt_und_lot, "quelle": quelle}
