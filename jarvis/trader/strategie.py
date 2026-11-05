"""
Entscheidungssystem des Trading-Roboters: BUY, SELL oder WAIT – immer mit Begründung.

1. Grundlage ist der regelbasierte Setup-Scanner (Pullback im H1-Trend, RSI/MACD drehen).
2. Gibt es ein Setup, bekommt es einen CONFIDENCE-SCORE (0–100) aus sechs nachvollziehbaren Teilen:

     H1-Trendstärke       bis 25   (wie steil steigt/fällt die EMA50 auf H1, gemessen in ATR)
     Pullback-Qualität    bis 20   (wie nah ist der Kurs an der EMA20 – näher = besserer Einstieg)
     Momentum-Wende       bis 20   (drehen RSI UND MACD in Trade-Richtung?)
     Chance/Risiko        bis 15   (CRV nach Kosten)
     Volatilität normal   bis 10   (weder tote Hose noch Chaos)
     H4-Rückenwind        bis 10   (liegt der Kurs auf H4 auf der richtigen Seite der EMA50?)

   WICHTIG: Der Score ist eine Punktwertung, KEINE Gewinnwahrscheinlichkeit. Ob z. B. "75" wirklich
   besser ist als "62", zeigt erst der Backtest/Paper-Test (Trefferquote je Score-Bereich) – erst
   dann ist er "kalibriert".
3. Kosten (Spread + Kommission) werden eingerechnet: Ist der Trade danach unattraktiv -> WAIT.

Die Funktion arbeitet nur mit ABGESCHLOSSENEN Kerzen (keine Entscheidung auf einer halben Kerze).
"""

from trading import indikatoren as ind
from trading import setups


def h4_aus_h1(kerzen_h1):
    """Fasst 1-Stunden-Kerzen zu 4-Stunden-Kerzen zusammen (nur vollständige Blöcke)."""
    bloecke = {}
    for k in kerzen_h1:
        block = k["zeit"] // (4 * 3600)
        b = bloecke.get(block)
        if b is None:
            bloecke[block] = dict(k, zeit=block * 4 * 3600, _n=1)
        else:
            b["high"], b["low"], b["close"], b["_n"] = max(b["high"], k["high"]), min(b["low"], k["low"]), k["close"], b["_n"] + 1
    return [{k: v for k, v in b.items() if k != "_n"} for _, b in sorted(bloecke.items()) if b["_n"] == 4]


def bewerten(kerzen, kerzen_h1, name, stellen=5, kosten=0.0):
    """
    kerzen:     abgeschlossene Kerzen des Einstiegs-Zeitrahmens (M15), ältester zuerst
    kerzen_h1:  abgeschlossene H1-Kerzen
    Gibt ein dict zurück: aktion (BUY/SELL/WAIT), confidence, teile, gruende, setup (Einstieg/Stop/Ziel)
    """
    e = setups.finde_setup(kerzen, kerzen_h1, name, stellen)
    if not e.get("setup"):
        return {"aktion": "WAIT", "confidence": 0, "teile": {}, "gruende": [e.get("grund") or "kein Setup"],
                "setup": None, "preis": e.get("preis")}
    s = dict(e["setup"])
    long = s["richtung"] == "LONG"
    risiko = abs(s["einstieg"] - s["stop"])
    chance = abs(s["ziel"] - s["einstieg"])
    crv_netto = (chance - kosten) / (risiko + kosten) if risiko + kosten > 0 else 0
    s["crv_netto"] = crv_netto
    s["kosten"] = kosten

    schluss = [k["close"] for k in kerzen]
    atr = ind.atr(kerzen)
    atr_jetzt = atr[-1]
    e20 = ind.ema(schluss, 20)
    rsi = ind.rsi(schluss)
    _, _, hist = ind.macd(schluss)
    h1_schluss = [k["close"] for k in kerzen_h1]
    h1_e50 = ind.ema(h1_schluss, 50)
    h1_atr = ind.atr(kerzen_h1)[-1] or atr_jetzt
    teile, gruende = {}, []

    steigung = (h1_e50[-1] - h1_e50[-11]) / h1_atr if h1_e50[-11] is not None and h1_atr else 0
    steigung = steigung if long else -steigung
    teile["H1-Trendstärke"] = 25 if steigung >= 1.5 else 18 if steigung >= 1.0 else 10 if steigung >= 0.5 else 0
    gruende.append(f"H1 {e['trend_h1']}, EMA50-Steigung {steigung:.1f} ATR")

    abstand = abs(schluss[-1] - e20[-1]) / atr_jetzt if atr_jetzt else 9
    teile["Pullback-Qualität"] = 20 if abstand <= 0.2 else 14 if abstand <= 0.4 else 8 if abstand <= 0.6 else 0
    gruende.append(f"Kurs {abstand:.2f} ATR von der EMA20 entfernt")

    rsi_dreht = (rsi[-1] > rsi[-2] > rsi[-3]) if long else (rsi[-1] < rsi[-2] < rsi[-3])
    macd_dreht = (hist[-1] > hist[-2] > hist[-3]) if long else (hist[-1] < hist[-2] < hist[-3])
    teile["Momentum-Wende"] = 20 if rsi_dreht and macd_dreht else 10 if rsi_dreht or macd_dreht else 0
    gruende.append(f"RSI {rsi[-1]:.0f} {'dreht' if rsi_dreht else 'dreht noch nicht klar'}, "
                   f"MACD {'dreht mit' if macd_dreht else 'noch zögerlich'}")

    teile["Chance/Risiko"] = 15 if crv_netto >= 2.5 else 12 if crv_netto >= 2.0 else 6 if crv_netto >= 1.5 else 0
    gruende.append(f"CRV nach Kosten {crv_netto:.2f}")

    letzte = [a for a in atr[-200:] if a is not None]
    rang = sum(1 for a in letzte if a <= atr_jetzt) / len(letzte) * 100 if letzte else 50
    teile["Volatilität normal"] = 10 if 20 <= rang <= 85 else 0
    gruende.append(f"Volatilität im {rang:.0f}. Perzentil" + ("" if teile["Volatilität normal"] else " – ungewöhnlich"))

    h4 = h4_aus_h1(kerzen_h1)
    h4_e50 = ind.ema([k["close"] for k in h4], 50)[-1] if len(h4) >= 50 else None
    if h4_e50 is None:
        teile["H4-Rückenwind"] = 5
        gruende.append("H4: zu wenig Daten")
    else:
        rueckenwind = (schluss[-1] > h4_e50) if long else (schluss[-1] < h4_e50)
        teile["H4-Rückenwind"] = 10 if rueckenwind else 0
        gruende.append(f"H4 {'unterstützt' if rueckenwind else 'spricht dagegen'} (Kurs {'über' if schluss[-1] > h4_e50 else 'unter'} EMA50)")

    return {"aktion": "BUY" if long else "SELL", "confidence": sum(teile.values()), "teile": teile,
            "gruende": gruende, "setup": s, "preis": schluss[-1]}
