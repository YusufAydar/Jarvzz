"""
Täglicher Trading-Bericht (Markdown), wird um Handelsschluss automatisch erstellt und unter
daten/trading_berichte/JJJJ-MM-TT.md gespeichert. Keine Trades sind ein gültiges Ergebnis.
"""

from trader import paper, risiko


def _trades_vom_tag(engine, tag):
    return [t for t in engine.konto.zustand["trades"] if risiko.tagesbeginn(t["geschlossen"]) == tag]


def _entscheidungen_vom_tag(engine, tag):
    return [e for e in engine.entscheidungen if risiko.tagesbeginn(e["zeit"]) == tag]


def kurzfassung(engine, tag):
    s = paper.statistik(_trades_vom_tag(engine, tag), engine.konto.zustand["tagesstart_equity"])
    if not s["trades"]:
        return "Heute keine Trades – es gab kein Signal, das alle Kriterien erfüllt hat."
    return (f"Heute {s['trades']} Trade(s), {s['gewinner']} im Plus, Ergebnis {s['netto']:+.0f} Dollar.")


def tagesbericht(engine, tag):
    konto = engine.konto.zustand
    trades = _trades_vom_tag(engine, tag)
    heute = paper.statistik(trades, konto["tagesstart_equity"])
    gesamt = paper.statistik(konto["trades"], konto["start"])
    entscheidungen = _entscheidungen_vom_tag(engine, tag)
    f = lambda x, n=2: "–" if x is None else ("∞" if x == float("inf") else f"{x:.{n}f}")
    zeilen = [f"# Trading-Tagesbericht {tag} (PAPER, Stufe {engine.stufe})", "",
              "## Marktübersicht", ""]
    for symbol, info in engine.markt_info.items():
        if info.get("fehler"):
            zeilen.append(f"- **{symbol}**: {info['fehler']}")
        else:
            signale = [e for e in entscheidungen if e["symbol"] == symbol and e["aktion"] in ("BUY", "SELL")]
            zeilen.append(f"- **{symbol}**: zuletzt {info['preis']:.{info['stellen']}f} ({info['quelle']}), "
                          f"{len(signale)} Signal(e)/Trade-Aktion(en) heute")
    chancen = [e for e in entscheidungen if e.get("confidence") and e["aktion"] in ("BUY", "SELL", "WAIT")
               and e["confidence"] >= 50]
    if chancen:
        zeilen += ["", "Erkannte Chancen:"] + [f"- {e['symbol']} {e['aktion']} (Confidence {e['confidence']}): "
                                                f"{e['gruende'][0]}" for e in chancen[:8]]
    zeilen += ["", "## Trading-Aktivitäten", "",
               f"- Eröffnet/geschlossen heute: {heute['trades']} geschlossen, {len(konto['offene'])} noch offen",
               f"- Profitabel: {heute['gewinner']}, verlustreich: {heute['verlierer']}"]
    for t in trades:
        zeilen.append(f"  - {t['symbol']} {t['richtung']} {t['einstieg']} → {t['ausstieg']} ({t['grund']}): "
                      f"{t['ergebnis']:+.2f} $ / {t['r']:+.2f} R, Confidence {t['confidence']}")
    zeilen += ["", "## Performance", "",
               f"- Tagesergebnis: {heute['netto']:+.2f} $",
               f"- Gesamt seit Start: {gesamt['netto']:+.2f} $ (Konto {konto['balance']:.2f} $)",
               f"- Win-Rate gesamt: {f((gesamt['win_rate'] or 0) * 100, 0)} %, Profit-Faktor {f(gesamt['profit_faktor'])}, "
               f"max. Drawdown {gesamt['max_drawdown_prozent']:.1f} %", "",
               "## Strategieanalyse", ""]
    waits = [e for e in entscheidungen if e["aktion"] == "WAIT"]
    gruende = {}
    for e in waits:
        g = e["gruende"][0].split(":")[0].split(" – ")[0][:60] if e["gruende"] else "?"
        gruende[g] = gruende.get(g, 0) + 1
    if gruende:
        zeilen.append("Häufigste Gründe, NICHT zu handeln: " + ", ".join(
            f"{k} ({v}x)" for k, v in sorted(gruende.items(), key=lambda x: -x[1])[:5]))
    if gesamt["trades"] < 30:
        zeilen.append(f"Noch zu wenige Trades ({gesamt['trades']}) für Schlussfolgerungen – Parameter bleiben unverändert.")
    zeilen += ["", "_Paper-Trading mit virtuellem Geld. Keine Anlageberatung._"]
    return "\n".join(zeilen) + "\n"
