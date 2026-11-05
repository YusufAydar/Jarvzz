"""
Mehrere bekannte Daytrading-Strategien – alle mit derselben Schnittstelle, damit Backtest, Engine und
Vergleich sie gleich behandeln können.

  pullback      Trend-Pullback: im H1-Trend an der EMA20 einsteigen, wenn RSI/MACD drehen (bisherige Strategie)
  orb_london    London-Opening-Range-Breakout: Spanne 09:00–10:00 (österreichische Zeit), erster
                Schlusskurs außerhalb zwischen 10:00 und 13:00 -> Einstieg, Stop an der anderen Seite (max. 2 ATR),
                Ziel 2R. Nur in Richtung des H1-Trends oder bei neutralem Trend.
  orb_newyork   Dasselbe zur US-Eröffnung: Spanne 15:30–16:00, Einstieg 16:00–19:00
  mean_reversion  Nur in Seitwärtsphasen (H1): Kurs schließt nach einem Ausflug außerhalb der Bollinger-Bänder
                (20, 2) wieder innerhalb, RSI war < 30 bzw. > 70 -> Einstieg Richtung Mitte, Stop hinter dem
                Extrem (+0,3 ATR), Ziel = mittleres Band (mind. CRV 1)

Jede Funktion bekommt ABGESCHLOSSENE Kerzen und gibt zurück:
  {"aktion": BUY/SELL/WAIT, "confidence": 0..100, "teile": {...}, "gruende": [...], "setup": {...} oder None}
"""

from trader import risiko, strategie
from trading import indikatoren as ind

ORB_ZEITEN = {"orb_london": ("09:00", "10:00", "13:00"), "orb_newyork": ("15:30", "16:00", "19:00")}


def _warten(grund, preis=None):
    return {"aktion": "WAIT", "confidence": 0, "teile": {}, "gruende": [grund], "setup": None, "preis": preis}


def _setup(richtung, einstieg, stop, ziel, kosten):
    risiko_punkte = abs(einstieg - stop)
    chance = abs(ziel - einstieg)
    return {"richtung": richtung, "einstieg": einstieg, "stop": stop, "ziel": ziel,
            "crv": chance / risiko_punkte if risiko_punkte else 0, "risiko_punkte": risiko_punkte,
            "crv_netto": (chance - kosten) / (risiko_punkte + kosten) if risiko_punkte + kosten > 0 else 0,
            "kosten": kosten}


def pullback(kerzen, kerzen_h1, name, stellen=5, kosten=0.0):
    return strategie.bewerten(kerzen, kerzen_h1, name, stellen, kosten)


def _orb(art, kerzen, kerzen_h1, name, stellen, kosten):
    beginn, ende, letzter_einstieg = ORB_ZEITEN[art]
    letzte = kerzen[-1]
    jetzt = risiko.wien_zeit(letzte["zeit"] + 900)            # Ende der gerade abgeschlossenen Kerze
    hm, tag = jetzt.strftime("%H:%M"), jetzt.strftime("%Y-%m-%d")
    if not (ende < hm <= letzter_einstieg):
        return _warten(f"außerhalb des Einstiegsfensters {ende}–{letzter_einstieg}", letzte["close"])
    heute = [k for k in kerzen if risiko.wien_zeit(k["zeit"]).strftime("%Y-%m-%d") == tag]
    spanne = [k for k in heute if beginn <= risiko.wien_zeit(k["zeit"]).strftime("%H:%M") < ende]
    if len(spanne) < 2:
        return _warten("Eröffnungsspanne unvollständig (Feiertag/Lücke)", letzte["close"])
    hoch, tief = max(k["high"] for k in spanne), min(k["low"] for k in spanne)
    danach = [k for k in heute if risiko.wien_zeit(k["zeit"]).strftime("%H:%M") >= ende]
    atr = ind.atr(kerzen)[-1]
    if not atr:
        return _warten("keine Schwankung messbar", letzte["close"])
    breite = hoch - tief
    # Nur der ERSTE Schlusskurs außerhalb der Spanne zählt (ein Trade pro Tag und Richtung)
    vorher = danach[:-1]
    nach_oben = letzte["close"] > hoch and all(k["close"] <= hoch for k in vorher)
    nach_unten = letzte["close"] < tief and all(k["close"] >= tief for k in vorher)
    if not (nach_oben or nach_unten):
        return _warten(f"kein frischer Ausbruch aus der Spanne {tief:.{stellen}f}–{hoch:.{stellen}f}", letzte["close"])
    trend_h1 = ind.trend(kerzen_h1) if kerzen_h1 and len(kerzen_h1) >= 60 else "unbekannt"
    if (nach_oben and trend_h1 == "Abwärtstrend") or (nach_unten and trend_h1 == "Aufwärtstrend"):
        return _warten(f"Ausbruch gegen den H1-Trend ({trend_h1})", letzte["close"])
    if breite > 2.5 * atr * 4 or breite < 0.3 * atr:
        return _warten("Spanne ungewöhnlich groß oder klein", letzte["close"])
    einstieg = letzte["close"]
    stop = (max(tief, einstieg - 2 * atr * 2) if nach_oben else min(hoch, einstieg + 2 * atr * 2))
    risiko_punkte = abs(einstieg - stop)
    ziel = einstieg + 2 * risiko_punkte if nach_oben else einstieg - 2 * risiko_punkte
    s = _setup("LONG" if nach_oben else "SHORT", einstieg, stop, ziel, kosten)
    teile = {"Trend passt": 30 if trend_h1 in ("Aufwärtstrend", "Abwärtstrend") else 15,
             "Saubere Spanne": 20 if 0.6 * atr <= breite <= 3 * atr else 10,
             "Kräftiger Ausbruch": 20 if abs(letzte["close"] - letzte["open"]) >= 0.5 * atr else 8,
             "Chance/Risiko": 20 if s["crv_netto"] >= 1.8 else 10 if s["crv_netto"] >= 1.5 else 0,
             "Früher Ausbruch": 10 if len(vorher) <= 4 else 4}
    gruende = [f"{'London' if art == 'orb_london' else 'New York'}-Spanne {tief:.{stellen}f}–{hoch:.{stellen}f}, "
               f"erster Schlusskurs {'darüber' if nach_oben else 'darunter'}", f"H1 {trend_h1}",
               f"Stop {stop:.{stellen}f}, Ziel {ziel:.{stellen}f} (2R), CRV nach Kosten {s['crv_netto']:.2f}"]
    return {"aktion": "BUY" if nach_oben else "SELL", "confidence": sum(teile.values()), "teile": teile,
            "gruende": gruende, "setup": s, "preis": einstieg}


def orb_london(kerzen, kerzen_h1, name, stellen=5, kosten=0.0):
    return _orb("orb_london", kerzen, kerzen_h1, name, stellen, kosten)


def orb_newyork(kerzen, kerzen_h1, name, stellen=5, kosten=0.0):
    return _orb("orb_newyork", kerzen, kerzen_h1, name, stellen, kosten)


def mean_reversion(kerzen, kerzen_h1, name, stellen=5, kosten=0.0):
    if len(kerzen) < 60:
        return _warten("zu wenig Daten")
    trend_h1 = ind.trend(kerzen_h1) if kerzen_h1 and len(kerzen_h1) >= 60 else "unbekannt"
    preis = kerzen[-1]["close"]
    if trend_h1 != "Seitwärts":
        return _warten(f"H1 {trend_h1} – Mean-Reversion nur in Seitwärtsphasen", preis)
    schluss = [k["close"] for k in kerzen]
    mitte, oben, unten = ind.bollinger(schluss, 20, 2.0)
    rsi = ind.rsi(schluss)
    atr = ind.atr(kerzen)[-1]
    k0, k1 = kerzen[-1], kerzen[-2]
    zurueck_von_unten = k1["close"] < unten[-2] and k0["close"] > unten[-1] and min(rsi[-3:-1]) < 30
    zurueck_von_oben = k1["close"] > oben[-2] and k0["close"] < oben[-1] and max(rsi[-3:-1]) > 70
    if not (zurueck_von_unten or zurueck_von_oben):
        return _warten("keine Übertreibung mit Rückkehr ins Bollinger-Band", preis)
    if zurueck_von_unten:
        extrem = min(k["low"] for k in kerzen[-4:])
        stop, ziel, richtung = extrem - 0.3 * atr, mitte[-1], "LONG"
    else:
        extrem = max(k["high"] for k in kerzen[-4:])
        stop, ziel, richtung = extrem + 0.3 * atr, mitte[-1], "SHORT"
    s = _setup(richtung, preis, stop, ziel, kosten)
    if s["crv"] < 1.0:
        return _warten(f"Mitte zu nah (CRV {s['crv']:.2f})", preis)
    teile = {"Seitwärtsphase": 30, "RSI-Extrem": 25 if (min(rsi[-3:-1]) < 25 or max(rsi[-3:-1]) > 75) else 15,
             "Chance/Risiko": 25 if s["crv_netto"] >= 1.8 else 15 if s["crv_netto"] >= 1.3 else 5,
             "Ruhiger Markt": 20 if (oben[-1] - unten[-1]) <= 6 * atr else 5}
    gruende = [f"H1 Seitwärts, Kurs kehrt von {'unten' if richtung == 'LONG' else 'oben'} ins Bollinger-Band zurück",
               f"RSI war {min(rsi[-3:-1]) if richtung == 'LONG' else max(rsi[-3:-1]):.0f}",
               f"Ziel Mitte {ziel:.{stellen}f}, CRV nach Kosten {s['crv_netto']:.2f}"]
    return {"aktion": "BUY" if richtung == "LONG" else "SELL", "confidence": sum(teile.values()), "teile": teile,
            "gruende": gruende, "setup": s, "preis": preis}


STRATEGIEN = {"pullback": pullback, "orb_london": orb_london, "orb_newyork": orb_newyork,
              "mean_reversion": mean_reversion}
NAMEN = {"pullback": "Trend-Pullback", "orb_london": "London-Breakout", "orb_newyork": "New-York-Breakout",
         "mean_reversion": "Mean-Reversion"}
# Mean-Reversion zielt nur auf die Mitte des Bandes – dort ist ein kleineres CRV normal (dafür höhere Trefferquote)
MIN_CRV = {"mean_reversion": 1.0}


def bewerten(name_strategie, kerzen, kerzen_h1, symbol, stellen=5, kosten=0.0):
    """Ruft die gewünschte Strategie auf und vermerkt ihren Namen im Signal."""
    if name_strategie not in STRATEGIEN:
        raise ValueError(f"Unbekannte Strategie {name_strategie} – möglich: {', '.join(STRATEGIEN)}")
    signal = STRATEGIEN[name_strategie](kerzen, kerzen_h1, symbol, stellen, kosten)
    signal["strategie"] = NAMEN[name_strategie]
    if signal.get("setup") and name_strategie in MIN_CRV:
        signal["setup"]["min_crv"] = MIN_CRV[name_strategie]
    return signal
