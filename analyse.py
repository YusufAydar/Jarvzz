"""
Wertet die Trades eines Traders aus.

Wichtigster Begriff: Ein einzelner "Fill" ist nur ein Teil-Kauf oder -Verkauf.
Ein echter "Trade" (Position) beginnt, wenn ein Coin von 0 auf eine Position geht,
und endet, wenn die Position wieder bei 0 ist (oder von Long auf Short dreht).
Diese Datei baut aus den vielen Fills die echten Trades zusammen und rechnet dann:
Gewinnrate, Gewinn/Verlust, Haltedauer, Lieblings-Coins, Hebel, größter Verlust.
"""

# Sehr kleine Zahlen gelten als 0 (Rundungsfehler bei Kommazahlen)
FAST_NULL = 1e-9


def ist_spot(coin):
    """Spot-Coins heißen bei Hyperliquid z. B. "@107" oder "PURR/USDC"."""
    return coin.startswith("@") or "/" in coin


def _vorzeichen(zahl):
    if zahl > FAST_NULL:
        return 1
    if zahl < -FAST_NULL:
        return -1
    return 0


def baue_trades(fills):
    """
    Macht aus einer Liste von Fills (ältester zuerst) eine Liste von Trades.

    Jeder Trade ist ein dict mit:
      coin, richtung ("Long"/"Short"), start, ende (Millisekunden),
      pnl (Gewinn minus Gebühren), vollstaendig (False, wenn der Anfang
      vor unseren Daten liegt – dann kennen wir die Haltedauer nicht).

    Gibt zwei Listen zurück: (abgeschlossene_trades, noch_offene_trades)
    """
    offen = {}          # coin -> aktuell laufender Trade
    abgeschlossen = []

    for f in fills:
        coin = f["coin"]
        if ist_spot(coin):
            continue  # Spot-Käufe haben keinen Hebel/Short – nur Perps werden ausgewertet

        vorher = f["start_position"]
        menge = f["menge"] if f["seite"] == "B" else -f["menge"]
        nachher = vorher + menge
        trade = offen.get(coin)

        if _vorzeichen(vorher) == 0:
            # Position war leer -> ein neuer Trade beginnt.
            # (Falls wir noch einen "offenen" hatten, fehlt uns dessen Ende -> verwerfen.)
            trade = _neuer_trade(coin, f["zeit"], menge, vollstaendig=True)
            offen[coin] = trade
        elif trade is None:
            # Position lief schon, bevor unsere Daten beginnen
            trade = _neuer_trade(coin, None, vorher, vollstaendig=False)
            offen[coin] = trade

        trade["pnl"] += f["closed_pnl"] - f["gebuehr"]
        trade["fills"] += 1

        vz_vorher, vz_nachher = _vorzeichen(vorher), _vorzeichen(nachher)
        if vz_vorher != 0 and vz_nachher != vz_vorher:
            # Position ist geschlossen (bei 0) oder hat die Seite gewechselt
            trade["ende"] = f["zeit"]
            abgeschlossen.append(trade)
            del offen[coin]
            if vz_nachher != 0:
                # Seitenwechsel: gleich ein neuer Trade in die andere Richtung
                offen[coin] = _neuer_trade(coin, f["zeit"], nachher, vollstaendig=True)

    return abgeschlossen, list(offen.values())


def _neuer_trade(coin, start, groesse, vollstaendig):
    return {
        "coin": coin,
        "richtung": "Long" if groesse > 0 else "Short",
        "start": start,
        "ende": None,
        "pnl": 0.0,
        "fills": 0,
        "vollstaendig": vollstaendig,
    }


def werte_aus(fills, positionen=None, kontowert=0.0):
    """
    Berechnet alle Kennzahlen für einen Trader.
    fills:      alle Fills des Traders (ältester zuerst)
    positionen: aktuell offene Positionen (für den Hebel)
    kontowert:  aktueller Kontowert in Dollar
    """
    positionen = positionen or []
    trades, offene = baue_trades(fills)

    gewinner = [t for t in trades if t["pnl"] > 0]
    verlierer = [t for t in trades if t["pnl"] < 0]
    haltedauern = [t["ende"] - t["start"] for t in trades if t["vollstaendig"]]

    # Handelsvolumen pro Coin (Preis * Menge) -> zeigt die Lieblings-Coins
    volumen = {}
    for f in fills:
        volumen[f["coin"]] = volumen.get(f["coin"], 0.0) + f["preis"] * f["menge"]
    gesamt_volumen = sum(volumen.values())
    lieblings_coins = sorted(volumen.items(), key=lambda x: x[1], reverse=True)[:3]

    # Hebel aus den offenen Positionen (die Historie enthält keinen Hebel)
    pos_werte = sum(abs(p["positionswert"]) for p in positionen)
    if pos_werte > 0:
        hebel_schnitt = sum(p["hebel"] * abs(p["positionswert"]) for p in positionen) / pos_werte
    else:
        hebel_schnitt = None
    hebel_max = max((p["hebel"] for p in positionen), default=None)
    # "Effektiver" Hebel = wie viel Position im Verhältnis zum Konto
    hebel_effektiv = pos_werte / kontowert if kontowert > 0 and pos_werte > 0 else None

    return {
        "anzahl_fills": len(fills),
        "anzahl_trades": len(trades),
        "offene_trades": len(offene),
        "gewinnrate": len(gewinner) / len(trades) if trades else None,
        "pnl_gesamt": sum(f["closed_pnl"] - f["gebuehr"] for f in fills),
        "pnl_trades": sum(t["pnl"] for t in trades),
        "durchschnitt_gewinn": sum(t["pnl"] for t in gewinner) / len(gewinner) if gewinner else None,
        "durchschnitt_verlust": sum(t["pnl"] for t in verlierer) / len(verlierer) if verlierer else None,
        "groesster_gewinn": max((t for t in trades), key=lambda t: t["pnl"], default=None),
        "groesster_verlust": min(verlierer, key=lambda t: t["pnl"], default=None),
        "haltedauer_schnitt_ms": sum(haltedauern) / len(haltedauern) if haltedauern else None,
        "lieblings_coins": [(coin, vol / gesamt_volumen) for coin, vol in lieblings_coins]
                           if gesamt_volumen else [],
        "hebel_schnitt": hebel_schnitt,
        "hebel_max": hebel_max,
        "hebel_effektiv": hebel_effektiv,
        "erster_fill": fills[0]["zeit"] if fills else None,
        "letzter_fill": fills[-1]["zeit"] if fills else None,
    }


def aktivitaet(fills):
    """
    Fasst zusammen, was ein Trader in einem Zeitraum (z. B. 24 h) gemacht hat.
    Gibt pro Coin zurück: gekauft ($), verkauft ($), netto ($) und was eröffnet wurde.
    """
    pro_coin = {}
    for f in fills:
        c = pro_coin.setdefault(f["coin"], {"gekauft": 0.0, "verkauft": 0.0,
                                            "long_eroeffnet": False, "short_eroeffnet": False})
        wert = f["preis"] * f["menge"]
        if f["seite"] == "B":
            c["gekauft"] += wert
        else:
            c["verkauft"] += wert
        richtung = f["richtung"] or ""
        if richtung in ("Open Long", "Short > Long"):
            c["long_eroeffnet"] = True
        if richtung in ("Open Short", "Long > Short"):
            c["short_eroeffnet"] = True
    for c in pro_coin.values():
        c["netto"] = c["gekauft"] - c["verkauft"]
    return pro_coin


def einigkeit(aktivitaeten, min_trader, min_anteil):
    """
    Findet Coins, bei denen sich die Trader einig sind.

    aktivitaeten: {wallet: aktivitaet(...)} – Ergebnis von aktivitaet() pro Trader
    Ein Trader zählt als "Käufer", wenn er netto mehr gekauft als verkauft hat.

    Gibt eine Liste pro Coin zurück, sortiert nach Handelsvolumen.
    """
    coins = {}
    for wallet, pro_coin in aktivitaeten.items():
        for coin, a in pro_coin.items():
            c = coins.setdefault(coin, {"coin": coin, "kaeufer": 0, "verkaeufer": 0,
                                        "netto": 0.0, "volumen": 0.0})
            if a["netto"] > 0:
                c["kaeufer"] += 1
            elif a["netto"] < 0:
                c["verkaeufer"] += 1
            c["netto"] += a["netto"]
            c["volumen"] += a["gekauft"] + a["verkauft"]

    ergebnis = []
    for c in coins.values():
        aktive = c["kaeufer"] + c["verkaeufer"]
        c["aktive"] = aktive
        if aktive >= min_trader and max(c["kaeufer"], c["verkaeufer"]) / aktive >= min_anteil:
            c["einig"] = "KAUFEN" if c["kaeufer"] > c["verkaeufer"] else "VERKAUFEN"
        else:
            c["einig"] = None
        ergebnis.append(c)
    ergebnis.sort(key=lambda c: c["volumen"], reverse=True)
    return ergebnis


def positions_einigkeit(alle_positionen, min_trader, min_anteil):
    """
    Wie einigkeit(), aber für die aktuell offenen Positionen:
    Wie viele Top-Trader sind gerade Long, wie viele Short?
    alle_positionen: Liste aller offenen Positionen aller Trader
    """
    coins = {}
    for p in alle_positionen:
        c = coins.setdefault(p["coin"], {"coin": p["coin"], "long": 0, "short": 0,
                                         "wert_long": 0.0, "wert_short": 0.0})
        if p["groesse"] > 0:
            c["long"] += 1
            c["wert_long"] += abs(p["positionswert"])
        elif p["groesse"] < 0:
            c["short"] += 1
            c["wert_short"] += abs(p["positionswert"])

    ergebnis = []
    for c in coins.values():
        anzahl = c["long"] + c["short"]
        c["anzahl"] = anzahl
        if anzahl >= min_trader and max(c["long"], c["short"]) / anzahl >= min_anteil:
            c["einig"] = "LONG" if c["long"] > c["short"] else "SHORT"
        else:
            c["einig"] = None
        ergebnis.append(c)
    ergebnis.sort(key=lambda c: c["wert_long"] + c["wert_short"], reverse=True)
    return ergebnis
