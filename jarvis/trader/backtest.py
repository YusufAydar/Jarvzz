"""
Backtester: spielt die Strategie auf historischen Kerzen durch – mit GENAU derselben Strategie,
Risiko-Engine und Paper-Logik wie im Live-Betrieb.

Ehrliche Regeln, damit das Ergebnis nicht geschönt ist:
- Entschieden wird am Ende einer Kerze, eingestiegen erst zum Eröffnungskurs der NÄCHSTEN Kerze.
- Kosten (Spread + Kommission) werden bei jedem Trade abgezogen.
- Werden Stop-Loss und Take-Profit in derselben Kerze berührt, zählt der Stop-Loss.
- Daytrading: Positionen werden vor Handelsschluss geschlossen.
- News-Sperre gibt es im Backtest nicht (keine historischen News-Daten) – live ist sie aktiv.

Zusätzlich: Ergebnis je Confidence-Bereich (Kalibrierung), Stabilität (erste 2/3 gegen letztes 1/3)
und Monte-Carlo (Trades 1000-mal neu gemischt -> realistischer schlimmster Drawdown).
"""

import bisect
import random

from trader import paper, risiko, strategie, strategien  # noqa: F401


def h1_aus_m15(kerzen):
    """Baut aus M15-Kerzen H1-Kerzen. Jede bekommt 'ende' = Zeitpunkt, ab dem sie abgeschlossen ist."""
    stunden = {}
    for k in kerzen:
        h = k["zeit"] // 3600
        s = stunden.get(h)
        if s is None:
            stunden[h] = dict(k, zeit=h * 3600)
        else:
            s["high"], s["low"], s["close"] = max(s["high"], k["high"]), min(s["low"], k["low"]), k["close"]
    return [dict(s, ende=h * 3600 + 3600) for h, s in sorted(stunden.items())]


def stellen_schaetzen(preis):
    return 2 if preis >= 100 else 3 if preis >= 10 else 5


def backtest(symbol, kerzen, regeln, start=10000.0, kerzen_h1=None, fenster=300, strategie_name="pullback"):
    """kerzen: M15-Kerzen (ältester zuerst). Gibt ein dict mit Trades, Statistik und Auswertungen zurück.
    strategie_name: eine aus trader.strategien.STRATEGIEN (Standard: Trend-Pullback)."""
    if len(kerzen) < fenster + 50:
        raise ValueError(f"Zu wenig Kursdaten für einen Backtest ({len(kerzen)} Kerzen).")
    h1 = [dict(k, ende=k["zeit"] + 3600) for k in kerzen_h1] if kerzen_h1 else h1_aus_m15(kerzen)
    h1_enden = [k["ende"] for k in h1]
    kosten = regeln.kosten.get(symbol.upper(), 0.0)
    schritt = regeln.einheiten_schritt.get(symbol.upper(), 0.01)
    stellen = stellen_schaetzen(kerzen[-1]["close"])
    konto = paper.PaperKonto(start)
    abgelehnt, warte_gruende, signale = {}, {}, 0

    for i in range(fenster, len(kerzen) - 1):
        k = kerzen[i]
        ende = k["zeit"] + 15 * 60
        konto.kerze_pruefen(symbol, k)
        konto.tag_pruefen(k["zeit"], {symbol: k["close"]})
        if konto.zustand["offene"]:
            t = risiko.wien_zeit(ende)
            if t.weekday() >= 5 or t.strftime("%H:%M") >= regeln.schliessen_um:
                konto.alle_schliessen({symbol: k["close"]}, ende, "Tagesende")
        if not risiko.in_handelszeit(ende, regeln) or konto.zustand["offene"]:
            continue
        h1_bis = bisect.bisect_right(h1_enden, ende)
        if h1_bis < 60:
            continue
        signal = strategien.bewerten(strategie_name, kerzen[i - fenster + 1:i + 1],
                                     h1[max(0, h1_bis - 250):h1_bis], symbol, stellen, kosten)
        if signal["aktion"] == "WAIT":
            grund = (signal["gruende"] or ["?"])[0].split(" – ")[0].split(",")[0]
            warte_gruende[grund] = warte_gruende.get(grund, 0) + 1
            continue
        signale += 1
        erlaubt, gruende = risiko.pruefen(signal, symbol, ende, konto.risiko_daten({symbol: k["close"]}), regeln)
        if not erlaubt:
            for g in gruende:
                schluessel = g.split("(")[0].strip()
                abgelehnt[schluessel] = abgelehnt.get(schluessel, 0) + 1
            continue
        naechste = kerzen[i + 1]
        einstieg = naechste["open"]
        s = signal["setup"]
        long = s["richtung"] == "LONG"
        if (long and not s["stop"] < einstieg < s["ziel"]) or (not long and not s["ziel"] < einstieg < s["stop"]):
            abgelehnt["Kurs ist schon über Stop/Ziel hinaus gesprungen"] = abgelehnt.get(
                "Kurs ist schon über Stop/Ziel hinaus gesprungen", 0) + 1
            continue
        einheiten = risiko.positionsgroesse(konto.equity(), regeln.risiko_prozent, einstieg, s["stop"], kosten, schritt)
        if einheiten <= 0:
            continue
        konto.eroeffnen(symbol, signal, einheiten, naechste["zeit"], preis=einstieg)

    letzte = kerzen[-1]
    konto.alle_schliessen({symbol: letzte["close"]}, letzte["zeit"] + 900, "Ende des Backtests")
    trades = konto.zustand["trades"]
    return {"symbol": symbol, "strategie": strategien.NAMEN[strategie_name], "von": kerzen[fenster]["zeit"], "bis": letzte["zeit"], "kerzen": len(kerzen),
            "start": start, "ende_balance": konto.zustand["balance"], "signale": signale, "trades": trades,
            "statistik": paper.statistik(trades, start), "kalibrierung": kalibrierung(trades),
            "stabilitaet": stabilitaet(trades, start), "monte_carlo": monte_carlo(trades, start),
            "quartale": quartale(trades),
            "abgelehnt": abgelehnt, "warte_gruende": warte_gruende}


def quartale(trades):
    """Ergebnis je Quartal – zeigt, ob die Strategie über die Zeit gleichmäßig funktioniert."""
    from datetime import datetime
    q = {}
    for t in trades:
        d = datetime.fromtimestamp(t["geschlossen"])
        name = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        x = q.setdefault(name, {"trades": 0, "summe_r": 0.0, "netto": 0.0})
        x["trades"] += 1
        x["summe_r"] += t.get("r") or 0
        x["netto"] += t["ergebnis"]
    return dict(sorted(q.items()))


def kalibrierung(trades):
    """Trefferquote je Confidence-Bereich – zeigt, ob ein höherer Score wirklich besser ist."""
    bereiche = {}
    for t in trades:
        c = t.get("confidence", 0)
        name = "80–100" if c >= 80 else "70–79" if c >= 70 else "60–69" if c >= 60 else "unter 60"
        b = bereiche.setdefault(name, {"trades": 0, "gewinner": 0, "summe_r": 0.0})
        b["trades"] += 1
        b["gewinner"] += t["ergebnis"] > 0
        b["summe_r"] += t.get("r") or 0
    return bereiche


def stabilitaet(trades, start):
    """Vergleicht die ersten zwei Drittel mit dem letzten Drittel (funktioniert es auch später noch?)."""
    if len(trades) < 6:
        return None
    sortiert = sorted(trades, key=lambda t: t["geschlossen"])
    grenze = len(sortiert) * 2 // 3
    return {"frueh": paper.statistik(sortiert[:grenze], start), "spaet": paper.statistik(sortiert[grenze:], start)}


def monte_carlo(trades, start, durchlaeufe=1000, seed=7):
    if len(trades) < 5:
        return None
    ergebnisse = [t["ergebnis"] for t in trades]
    zufall = random.Random(seed)
    drawdowns = []
    for _ in range(durchlaeufe):
        zufall.shuffle(ergebnisse)
        stand = hoch = start
        dd = 0.0
        for e in ergebnisse:
            stand += e
            hoch = max(hoch, stand)
            dd = max(dd, (hoch - stand) / hoch * 100)
        drawdowns.append(dd)
    drawdowns.sort()
    return {"median_drawdown": drawdowns[len(drawdowns) // 2], "drawdown_95": drawdowns[int(len(drawdowns) * 0.95)]}


def urteil(ergebnis, regeln):
    """Bestanden? Nur wenn genug Trades UND Profit-Faktor, Drawdown und Stabilität passen."""
    s = ergebnis["statistik"]
    if s["trades"] < 30:
        return "ZU WENIG DATEN", f"nur {s['trades']} Trades – für eine belastbare Aussage braucht es mindestens 30, besser 100+"
    probleme = []
    if (s["profit_faktor"] or 0) < 1.3:
        probleme.append(f"Profit-Faktor {s['profit_faktor']:.2f} unter 1,3")
    if s["max_drawdown_prozent"] > regeln.max_drawdown_prozent:
        probleme.append(f"Drawdown {s['max_drawdown_prozent']:.1f} % über {regeln.max_drawdown_prozent} %")
    mc = ergebnis["monte_carlo"]
    if mc and mc["drawdown_95"] > regeln.max_drawdown_prozent * 1.5:
        probleme.append(f"Monte-Carlo: im schlechten Fall {mc['drawdown_95']:.1f} % Drawdown")
    st = ergebnis["stabilitaet"]
    if st and (st["spaet"]["profit_faktor"] or 0) < 1.0:
        probleme.append("im letzten Drittel nicht mehr profitabel")
    return ("BESTANDEN", "alle Kriterien erfüllt") if not probleme else ("NICHT BESTANDEN", "; ".join(probleme))


def text(ergebnis, regeln):
    from datetime import datetime
    s = ergebnis["statistik"]
    f = lambda x, n=2: "–" if x is None else ("∞" if x == float("inf") else f"{x:.{n}f}")
    status, warum = urteil(ergebnis, regeln)
    zeilen = [
        f"BACKTEST {ergebnis['symbol']} – {ergebnis.get('strategie', 'Trend-Pullback')} (M15), {datetime.fromtimestamp(ergebnis['von']):%d.%m.%Y} bis "
        f"{datetime.fromtimestamp(ergebnis['bis']):%d.%m.%Y}, {ergebnis['kerzen']} Kerzen",
        f"Urteil: {status} – {warum}",
        f"Trades {s['trades']} (Signale {ergebnis['signale']}), Win-Rate {f((s['win_rate'] or 0) * 100, 0)} %, "
        f"Profit-Faktor {f(s['profit_faktor'])}, Netto {s['netto']:+.2f} $ (Gebühren {s['gebuehren']:.2f} $), "
        f"Ø {f(s['schnitt_r'])} R, max. Drawdown {s['max_drawdown_prozent']:.1f} %",
    ]
    if ergebnis["kalibrierung"]:
        zeilen.append("Je Confidence: " + "; ".join(
            f"{k}: {v['gewinner']}/{v['trades']} gewonnen, {v['summe_r']:+.1f} R"
            for k, v in sorted(ergebnis["kalibrierung"].items())))
    st = ergebnis["stabilitaet"]
    if st:
        zeilen.append(f"Stabilität: erste 2/3 PF {f(st['frueh']['profit_faktor'])}, letztes 1/3 PF {f(st['spaet']['profit_faktor'])}")
    if ergebnis.get("quartale") and len(ergebnis["quartale"]) > 1:
        zeilen.append("Je Quartal: " + "; ".join(f"{k} {v['trades']} Trades {v['summe_r']:+.1f} R"
                                                  for k, v in ergebnis["quartale"].items()))
    mc = ergebnis["monte_carlo"]
    if mc:
        zeilen.append(f"Monte-Carlo: typischer Drawdown {mc['median_drawdown']:.1f} %, schlechter Fall (95 %) {mc['drawdown_95']:.1f} %")
    if ergebnis["abgelehnt"]:
        zeilen.append("Von der Risiko-Engine abgelehnt: " + ", ".join(
            f"{k} ({v}x)" for k, v in sorted(ergebnis["abgelehnt"].items(), key=lambda x: -x[1])[:4]))
    if ergebnis["warte_gruende"]:
        zeilen.append("Häufigste Gründe fürs Warten: " + ", ".join(
            f"{k} ({v}x)" for k, v in sorted(ergebnis["warte_gruende"].items(), key=lambda x: -x[1])[:3]))
    zeilen.append("Hinweis: Vergangene Ergebnisse garantieren nichts. Ohne News-Sperre getestet.")
    return "\n".join(zeilen)


def vergleich(symbol, kerzen, regeln, start=10000.0, namen=None, fenster=300):
    """Testet mehrere Strategien auf GENAU denselben Kursdaten. Gibt die Ergebnisse sortiert zurück (beste zuerst)."""
    ergebnisse = [backtest(symbol, kerzen, regeln, start, fenster=fenster, strategie_name=n)
                  for n in (namen or strategien.STRATEGIEN)]

    def rang(e):
        s = e["statistik"]
        status = urteil(e, regeln)[0]
        # Erst bestandene, dann nach Ø R je Trade (nur mit genug Trades zählt das wirklich)
        return (status == "BESTANDEN", s["trades"] >= 30, s["schnitt_r"] or -99)
    return sorted(ergebnisse, key=rang, reverse=True)


def vergleich_text(ergebnisse, regeln):
    """Kurze Tabelle für den Vergleich mehrerer Strategien auf einem Markt."""
    f = lambda x, n=2: "–" if x is None else ("∞" if x == float("inf") else f"{x:.{n}f}")
    zeilen = [f"STRATEGIE-VERGLEICH {ergebnisse[0]['symbol']}:"]
    for e in ergebnisse:
        s = e["statistik"]
        status = urteil(e, regeln)[0]
        st = e["stabilitaet"]
        zeilen.append(f"  {e['strategie']:<18} {s['trades']:>4} Trades, Win {f((s['win_rate'] or 0) * 100, 0):>3} %, "
                      f"PF {f(s['profit_faktor']):>5}, Ø {f(s['schnitt_r']):>5} R, Netto {s['netto']:+9.2f} $, "
                      f"DD {s['max_drawdown_prozent']:4.1f} %, spätes Drittel PF "
                      f"{f(st['spaet']['profit_faktor']) if st else '–'} -> {status}")
    return "\n".join(zeilen)
