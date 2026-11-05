"""
Technische Analyse: rechnet aus Kerzen (Candles) Trend, Indikatoren und wichtige Preiszonen.

Eine Kerze ist ein dict mit: zeit, open, high, low, close.
Alles in reinem Python – keine Zusatzpakete nötig.

Begriffe kurz erklärt:
- EMA:  gleitender Durchschnitt, der neue Kurse stärker gewichtet (zeigt die Richtung)
- RSI:  0–100. Über 70 = "überkauft" (oft zu schnell gestiegen), unter 30 = "überverkauft"
- MACD: Differenz zweier EMAs. Über der Signallinie = Schwung nach oben, darunter = nach unten
- ATR:  durchschnittliche Schwankung pro Kerze – gut für Stop-Loss-Abstände
- Unterstützung/Widerstand: Preise, an denen der Kurs schon mehrmals gedreht hat
- Pivot-Punkte: Tagesmarken aus Hoch/Tief/Schluss des Vortags – beliebt im Daytrading
"""


def ema(werte, n):
    """Exponentieller gleitender Durchschnitt. Gibt eine Liste gleicher Länge zurück (Anfang = None)."""
    if len(werte) < n:
        return [None] * len(werte)
    k = 2 / (n + 1)
    ergebnis = [None] * (n - 1)
    aktuell = sum(werte[:n]) / n  # Start mit einfachem Durchschnitt
    ergebnis.append(aktuell)
    for w in werte[n:]:
        aktuell = w * k + aktuell * (1 - k)
        ergebnis.append(aktuell)
    return ergebnis


def rsi(schluss, n=14):
    """Relative Strength Index nach Wilder."""
    if len(schluss) <= n:
        return [None] * len(schluss)
    gewinne = [max(schluss[i] - schluss[i - 1], 0) for i in range(1, len(schluss))]
    verluste = [max(schluss[i - 1] - schluss[i], 0) for i in range(1, len(schluss))]
    avg_g = sum(gewinne[:n]) / n
    avg_v = sum(verluste[:n]) / n
    ergebnis = [None] * n

    def wert(g, v):
        return 100.0 if v == 0 else 100 - 100 / (1 + g / v)

    ergebnis.append(wert(avg_g, avg_v))
    for g, v in zip(gewinne[n:], verluste[n:]):
        avg_g = (avg_g * (n - 1) + g) / n
        avg_v = (avg_v * (n - 1) + v) / n
        ergebnis.append(wert(avg_g, avg_v))
    return ergebnis


def macd(schluss, schnell=12, langsam=26, signal=9):
    """Gibt (macd_linie, signal_linie, histogramm) zurück."""
    e_s, e_l = ema(schluss, schnell), ema(schluss, langsam)
    linie = [a - b if a is not None and b is not None else None for a, b in zip(e_s, e_l)]
    gueltig = [x for x in linie if x is not None]
    sig_teil = ema(gueltig, signal)
    sig = [None] * (len(linie) - len(gueltig)) + sig_teil
    hist = [a - b if a is not None and b is not None else None for a, b in zip(linie, sig)]
    return linie, sig, hist


def atr(kerzen, n=14):
    """Average True Range nach Wilder."""
    if len(kerzen) <= n:
        return [None] * len(kerzen)
    tr = [kerzen[0]["high"] - kerzen[0]["low"]]
    for vorher, k in zip(kerzen, kerzen[1:]):
        tr.append(max(k["high"] - k["low"], abs(k["high"] - vorher["close"]), abs(k["low"] - vorher["close"])))
    ergebnis = [None] * (n - 1)
    aktuell = sum(tr[:n]) / n
    ergebnis.append(aktuell)
    for t in tr[n:]:
        aktuell = (aktuell * (n - 1) + t) / n
        ergebnis.append(aktuell)
    return ergebnis


def trend(kerzen):
    """
    Einfache, nachvollziehbare Trend-Regel:
      Aufwärts:  Kurs über EMA50, EMA20 über EMA50 und EMA50 steigt deutlich
      Abwärts:   genau umgekehrt
      sonst:     Seitwärts
    "Deutlich" heißt: Die EMA50 hat sich in 10 Kerzen um mehr als eine halbe ATR bewegt.
    So zählt normales Hin-und-her nicht als Trend.
    """
    schluss = [k["close"] for k in kerzen]
    e20, e50 = ema(schluss, 20), ema(schluss, 50)
    if e50[-1] is None or len(e50) < 11 or e50[-11] is None:
        return "unbekannt (zu wenig Daten)"
    schwelle = 0.5 * (atr(kerzen)[-1] or 0)
    steigung = e50[-1] - e50[-11]
    if schluss[-1] > e50[-1] and e20[-1] > e50[-1] and steigung > schwelle:
        return "Aufwärtstrend"
    if schluss[-1] < e50[-1] and e20[-1] < e50[-1] and steigung < -schwelle:
        return "Abwärtstrend"
    return "Seitwärts"


def preiszonen(kerzen, fenster=3, atr_wert=None):
    """
    Findet Unterstützungen und Widerstände aus Wendepunkten (Swing-Hochs/-Tiefs).
    Nahe beieinanderliegende Wendepunkte werden zu einer Zone zusammengefasst.
    Gibt (unterstuetzungen, widerstaende) zurück – jeweils Liste von (preis, beruehrungen),
    die nächstgelegenen zuerst.
    """
    punkte = []
    for i in range(fenster, len(kerzen) - fenster):
        bereich = kerzen[i - fenster:i + fenster + 1]
        if kerzen[i]["high"] == max(k["high"] for k in bereich):
            punkte.append(kerzen[i]["high"])
        if kerzen[i]["low"] == min(k["low"] for k in bereich):
            punkte.append(kerzen[i]["low"])
    if not punkte:
        return [], []
    toleranz = (atr_wert or (max(k["high"] for k in kerzen) - min(k["low"] for k in kerzen)) / 50) * 0.5
    zonen = []  # [summe, anzahl]
    for p in sorted(punkte):
        if zonen and p - zonen[-1][0] / zonen[-1][1] <= toleranz:
            zonen[-1][0] += p
            zonen[-1][1] += 1
        else:
            zonen.append([p, 1])
    preis = kerzen[-1]["close"]
    zonen = [(s / n, n) for s, n in zonen]
    unter = sorted([z for z in zonen if z[0] < preis], key=lambda z: preis - z[0])
    ueber = sorted([z for z in zonen if z[0] > preis], key=lambda z: z[0] - preis)
    return unter[:3], ueber[:3]


def pivot_punkte(vortag):
    """Klassische Pivot-Punkte aus der Tageskerze des Vortags."""
    h, l, c = vortag["high"], vortag["low"], vortag["close"]
    pp = (h + l + c) / 3
    return {"PP": pp, "R1": 2 * pp - l, "S1": 2 * pp - h,
            "R2": pp + (h - l), "S2": pp - (h - l)}


def analysiere(kerzen, kerzen_h1=None, vortag=None):
    """Fasst alles zu einem dict zusammen."""
    schluss = [k["close"] for k in kerzen]
    atr_liste = atr(kerzen)
    m_linie, m_signal, m_hist = macd(schluss)
    e20, e50 = ema(schluss, 20), ema(schluss, 50)
    unter, ueber = preiszonen(kerzen[-150:], atr_wert=atr_liste[-1])
    ergebnis = {
        "preis": schluss[-1],
        "trend": trend(kerzen),
        "trend_h1": trend(kerzen_h1) if kerzen_h1 else None,
        "ema20": e20[-1], "ema50": e50[-1],
        "rsi": rsi(schluss)[-1],
        "macd": m_linie[-1], "macd_signal": m_signal[-1], "macd_hist": m_hist[-1],
        "macd_kreuzung": None,
        "atr": atr_liste[-1],
        "unterstuetzungen": unter, "widerstaende": ueber,
        "pivots": pivot_punkte(vortag) if vortag else None,
    }
    # Hat der MACD gerade (in den letzten 3 Kerzen) die Signallinie gekreuzt?
    for i in range(-3, 0):
        a, b = m_hist[i - 1], m_hist[i]
        if a is not None and b is not None:
            if a <= 0 < b:
                ergebnis["macd_kreuzung"] = "nach oben"
            elif a >= 0 > b:
                ergebnis["macd_kreuzung"] = "nach unten"
    return ergebnis


def zusammenfassung(symbol, zeitrahmen, a, stellen=5):
    """Macht aus dem Analyse-Ergebnis einen Text für Claude."""
    f = lambda x: "–" if x is None else f"{x:.{stellen}f}"
    zeilen = [f"{symbol} ({zeitrahmen}) – Preis {f(a['preis'])}",
              f"Trend {zeitrahmen}: {a['trend']}" + (f" | Trend H1: {a['trend_h1']}" if a["trend_h1"] else ""),
              f"EMA20 {f(a['ema20'])}, EMA50 {f(a['ema50'])}"]
    if a["rsi"] is not None:
        zustand = " (überkauft)" if a["rsi"] > 70 else " (überverkauft)" if a["rsi"] < 30 else ""
        zeilen.append(f"RSI(14): {a['rsi']:.1f}{zustand}")
    if a["macd_hist"] is not None:
        zeilen.append(f"MACD: {'über' if a['macd_hist'] > 0 else 'unter'} der Signallinie"
                      + (f", frische Kreuzung {a['macd_kreuzung']}" if a["macd_kreuzung"] else ""))
    zeilen.append(f"ATR(14): {f(a['atr'])} (typische Schwankung pro Kerze)")
    if a["unterstuetzungen"]:
        zeilen.append("Unterstützungen: " + ", ".join(f"{f(p)} ({n}x berührt)" for p, n in a["unterstuetzungen"]))
    if a["widerstaende"]:
        zeilen.append("Widerstände: " + ", ".join(f"{f(p)} ({n}x berührt)" for p, n in a["widerstaende"]))
    if a["pivots"]:
        zeilen.append("Tages-Pivots: " + ", ".join(f"{k} {f(v)}" for k, v in a["pivots"].items()))
    return "\n".join(zeilen)
