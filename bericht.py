"""
Erstellt den täglichen Bericht als Markdown-Datei.

Markdown ist ein einfaches Textformat. GitHub zeigt es automatisch
schön formatiert an (Überschriften, Tabellen, fette Schrift ...).
"""

from datetime import datetime, timezone

import analyse
import datenbank

TAG_MS = 24 * 60 * 60 * 1000


# ---------- Kleine Helfer, damit Zahlen schön aussehen ----------

def geld(betrag):
    """1234567.8 -> "+1.234.568 $" (deutsches Zahlenformat)"""
    if betrag is None:
        return "–"
    text = f"{abs(betrag):,.0f}".replace(",", ".")
    vorzeichen = "-" if betrag < 0 else ("+" if betrag > 0 else "")
    return f"{vorzeichen}{text} $"


def geld_ohne_vorzeichen(betrag):
    return f"{abs(betrag):,.0f}".replace(",", ".") + " $"


def prozent(anteil):
    if anteil is None:
        return "–"
    return f"{anteil * 100:.0f} %"


def dauer(ms):
    """Millisekunden -> gut lesbare Dauer, z. B. "3,5 Std" oder "2,1 Tage"."""
    if ms is None:
        return "–"
    minuten = ms / 60000
    if minuten < 60:
        return f"{minuten:.0f} Min"
    stunden = minuten / 60
    if stunden < 48:
        return f"{stunden:.1f} Std".replace(".", ",")
    return f"{stunden / 24:.1f} Tage".replace(".", ",")


def hebel(wert):
    return "–" if wert is None else f"{wert:.1f}x".replace(".", ",")


def kurz(wallet, name=None):
    """0x1234...abcd als Link zum Hyperliquid-Explorer"""
    text = name or f"{wallet[:6]}…{wallet[-4:]}"
    return f"[{text}](https://app.hyperliquid.xyz/explorer/address/{wallet})"


def datum(ms):
    if ms is None:
        return "–"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%d.%m.%Y")


# ---------- Der eigentliche Bericht ----------

def erstelle_bericht(db, jetzt_ms, min_trader, min_anteil):
    trader = datenbank.top_trader(db)
    seit_ms = jetzt_ms - TAG_MS
    jetzt_text = datetime.fromtimestamp(jetzt_ms / 1000, tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    aktivitaeten = {}      # was hat jeder Trader in den letzten 24 h gemacht?
    statistiken = {}       # Kennzahlen über die ganze gespeicherte Historie
    alle_positionen = []
    for t in trader:
        fills = datenbank.fills_von(db, t["wallet"])
        positionen = datenbank.positionen_von(db, t["wallet"])
        alle_positionen.extend(positionen)
        statistiken[t["wallet"]] = analyse.werte_aus(fills, positionen, t["kontowert"] or 0)
        letzte_24h = [f for f in fills if f["zeit"] >= seit_ms]
        aktivitaeten[t["wallet"]] = analyse.aktivitaet(letzte_24h)

    coins_24h = analyse.einigkeit(aktivitaeten, min_trader, min_anteil)
    coins_pos = analyse.positions_einigkeit(alle_positionen, min_trader, min_anteil)
    aktive_trader = sum(1 for a in aktivitaeten.values() if a)

    z = []  # z = Zeilen des Berichts
    z.append(f"# Hyperliquid Top-Trader – Tagesbericht {jetzt_text[:10]}")
    z.append("")
    z.append(f"Erstellt: {jetzt_text} · Analysierte Trader: **{len(trader)}** · "
             f"Davon in den letzten 24 h aktiv: **{aktive_trader}**")
    z.append("")
    z.append(f"> „Einig“ heißt: mindestens {min_trader} Trader handeln den Coin und "
             f"mindestens {prozent(min_anteil)} davon in dieselbe Richtung.")
    z.append("> Kein Anlagerat – nur eine Auswertung öffentlicher Daten.")
    z.append("")

    # 1) Einigkeit in den letzten 24 h
    z.append("## 1. Wo sind sich die Top-Trader einig? (letzte 24 Stunden)")
    z.append("")
    einig = [c for c in coins_24h if c["einig"]]
    if einig:
        for c in einig:
            symbol = "🟢" if c["einig"] == "KAUFEN" else "🔴"
            z.append(f"- {symbol} **{c['coin']}: {c['einig']}** – {c['kaeufer']} Käufer, "
                     f"{c['verkaeufer']} Verkäufer, netto {geld(c['netto'])}")
    else:
        z.append("Heute gab es keinen Coin mit klarer Einigkeit.")
    z.append("")

    # 2) Alle gehandelten Coins
    z.append("## 2. Was wurde in den letzten 24 Stunden gehandelt?")
    z.append("")
    if coins_24h:
        z.append("| Coin | Käufer | Verkäufer | Netto gekauft | Volumen | Einig? |")
        z.append("|---|---:|---:|---:|---:|---|")
        for c in coins_24h[:25]:
            z.append(f"| {c['coin']} | {c['kaeufer']} | {c['verkaeufer']} | {geld(c['netto'])} | "
                     f"{geld_ohne_vorzeichen(c['volumen'])} | {c['einig'] or ''} |")
        if len(coins_24h) > 25:
            z.append(f"\n_… und {len(coins_24h) - 25} weitere Coins mit weniger Volumen._")
    else:
        z.append("Keine Trades in den letzten 24 Stunden.")
    z.append("")

    # 3) Offene Positionen
    z.append("## 3. Offene Positionen gerade jetzt: Long oder Short?")
    z.append("")
    if coins_pos:
        z.append("| Coin | Long | Short | Wert Long | Wert Short | Einig? |")
        z.append("|---|---:|---:|---:|---:|---|")
        for c in coins_pos[:20]:
            z.append(f"| {c['coin']} | {c['long']} | {c['short']} | "
                     f"{geld_ohne_vorzeichen(c['wert_long'])} | {geld_ohne_vorzeichen(c['wert_short'])} | "
                     f"{c['einig'] or ''} |")
    else:
        z.append("Keine offenen Positionen gefunden.")
    z.append("")

    # 4) Was hat jeder einzelne Trader gemacht?
    z.append("## 4. Aktivität pro Trader (letzte 24 Stunden)")
    z.append("")
    z.append("| Rang | Trader | Gekauft | Verkauft | Wichtigste Coins (netto) |")
    z.append("|---:|---|---:|---:|---|")
    for t in trader:
        a = aktivitaeten[t["wallet"]]
        if not a:
            continue
        gekauft = sum(c["gekauft"] for c in a.values())
        verkauft = sum(c["verkauft"] for c in a.values())
        wichtig = sorted(a.items(), key=lambda x: abs(x[1]["netto"]), reverse=True)[:3]
        coins = ", ".join(f"{coin} {geld(c['netto'])}" for coin, c in wichtig)
        z.append(f"| {t['rang']} | {kurz(t['wallet'], t['name'])} | {geld_ohne_vorzeichen(gekauft)} | "
                 f"{geld_ohne_vorzeichen(verkauft)} | {coins} |")
    if aktive_trader == 0:
        z.append("| – | Niemand war aktiv | | | |")
    z.append("")

    # 5) Statistik pro Trader
    z.append("## 5. Statistik pro Trader (gesamte gespeicherte Historie)")
    z.append("")
    z.append("| Rang | Trader | PnL Monat (Rangliste) | Gewinnrate | PnL aus Trades | "
             "Trades | Ø Haltedauer | Lieblings-Coins | Hebel Ø / max | Größter Verlust | Daten ab |")
    z.append("|---:|---|---:|---:|---:|---:|---:|---|---|---:|---|")
    for t in trader:
        s = statistiken[t["wallet"]]
        lieblinge = ", ".join(f"{coin} {prozent(anteil)}" for coin, anteil in s["lieblings_coins"])
        verlust = s["groesster_verlust"]
        verlust_text = f"{geld(verlust['pnl'])} ({verlust['coin']})" if verlust else "–"
        z.append(
            f"| {t['rang']} | {kurz(t['wallet'], t['name'])} | {geld(t['pnl_monat'])} | "
            f"{prozent(s['gewinnrate'])} | {geld(s['pnl_trades'])} | {s['anzahl_trades']} | "
            f"{dauer(s['haltedauer_schnitt_ms'])} | {lieblinge or '–'} | "
            f"{hebel(s['hebel_schnitt'])} / {hebel(s['hebel_max'])} | {verlust_text} | "
            f"{datum(s['erster_fill'])} |")
    z.append("")
    z.append("**So liest du die Tabelle:**")
    z.append("- *Gewinnrate*: Anteil der abgeschlossenen Trades mit Gewinn.")
    z.append("- *PnL aus Trades*: Summe aller Gewinne und Verluste der gespeicherten Trades, nach Gebühren.")
    z.append("- *Hebel*: aus den gerade offenen Positionen (die API speichert den Hebel alter Trades nicht).")
    z.append("- *Daten ab*: Hyperliquid liefert nur die letzten 10.000 Trades pro Wallet. "
             "Bei sehr aktiven Tradern reicht die Historie deshalb nicht weit zurück.")
    z.append("")
    return "\n".join(z)
