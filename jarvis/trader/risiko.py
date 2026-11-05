"""
RISIKO-ENGINE – sie hat das letzte Wort. Egal wie gut ein Signal aussieht: Verstößt es gegen eine
Regel, wird es abgelehnt. Die Grenzen kommen aus den Einstellungen; der Roboter kann sie nicht ändern.

Kein Martingale: Das Risiko pro Trade ist immer ein fester Prozentsatz des AKTUELLEN Kontostands –
nach Verlusten wird die Position also kleiner, nie größer.
"""

from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    WIEN = ZoneInfo("Europe/Vienna")
except Exception:  # ohne Zeitzonen-Daten: Ortszeit des PCs
    WIEN = None

# Märkte, die sich stark gleich bewegen – nicht gleichzeitig in dieselbe Richtung handeln
KORRELATIONS_GRUPPEN = [{"US100", "US500", "US30", "GER40"}, {"EURUSD", "GBPUSD"}, {"BTCUSD", "ETHUSD"}]
NEWS_WAEHRUNGEN = {"XAUUSD": {"USD"}, "US100": {"USD"}, "US30": {"USD"}, "US500": {"USD"},
                   "EURUSD": {"USD", "EUR"}, "GBPUSD": {"USD", "GBP"}, "GER40": {"EUR"}, "BTCUSD": {"USD"}}


def wien_zeit(zeitstempel):
    dt = datetime.fromtimestamp(zeitstempel, WIEN) if WIEN else datetime.fromtimestamp(zeitstempel)
    return dt


class Regeln:
    """Alle Grenzen an einem Ort (aus einstellungen.py)."""

    def __init__(self, e):
        self.risiko_prozent = e.TRADER_RISIKO_PROZENT
        self.tagesstopp_prozent = e.TRADER_TAGESSTOPP_PROZENT
        self.max_drawdown_prozent = e.TRADER_MAX_DRAWDOWN_PROZENT
        self.max_positionen = e.TRADER_MAX_POSITIONEN
        self.verlustserie_pause = e.TRADER_VERLUSTSERIE_PAUSE
        self.min_confidence = e.TRADER_MIN_CONFIDENCE
        self.min_crv = e.TRADER_MIN_CRV
        self.handelszeit = e.TRADER_HANDELSZEIT
        self.schliessen_um = e.TRADER_SCHLIESSEN_UM
        self.news_sperre_minuten = e.TRADER_NEWS_SPERRE_MINUTEN
        self.kosten = dict(e.TRADER_KOSTEN)
        self.einheiten_schritt = dict(e.TRADER_EINHEITEN_SCHRITT)


def in_handelszeit(zeitstempel, regeln):
    t = wien_zeit(zeitstempel)
    if t.weekday() >= 5:
        return False
    hm = t.strftime("%H:%M")
    return regeln.handelszeit[0] <= hm < regeln.handelszeit[1] and hm < regeln.schliessen_um


def pruefen(signal, symbol, zeitstempel, konto, regeln, news=None):
    """
    signal:  Ergebnis von strategie.bewerten (aktion BUY/SELL)
    konto:   dict mit equity, tagesstart_equity, hoechststand, verlustserie, offene (Liste),
             status ("aktiv", "pausiert", "notaus", "gesperrt")
    news:    Liste wichtiger Termine [{"zeit": unix, "waehrung": "USD", "titel": ...}] (darf fehlen)
    Gibt (erlaubt, liste_der_gruende) zurück.
    """
    gruende = []
    if konto.get("status") != "aktiv":
        gruende.append(f"Roboter ist {konto.get('status')}")
    if not in_handelszeit(zeitstempel, regeln):
        gruende.append("außerhalb der Handelszeit")
    tagesverlust = (konto["tagesstart_equity"] - konto["equity"]) / konto["tagesstart_equity"] * 100
    if tagesverlust >= regeln.tagesstopp_prozent:
        gruende.append(f"Tagesstopp erreicht ({tagesverlust:.1f} % Verlust heute)")
    drawdown = (konto["hoechststand"] - konto["equity"]) / konto["hoechststand"] * 100
    if drawdown >= regeln.max_drawdown_prozent:
        gruende.append(f"Maximaler Drawdown erreicht ({drawdown:.1f} %)")
    if konto.get("verlustserie", 0) >= regeln.verlustserie_pause:
        gruende.append(f"{konto['verlustserie']} Verluste in Folge – Pause bis morgen")
    offene = konto.get("offene", [])
    if len(offene) >= regeln.max_positionen:
        gruende.append(f"schon {len(offene)} Positionen offen (Maximum {regeln.max_positionen})")
    if any(p["symbol"] == symbol for p in offene):
        gruende.append(f"schon eine Position in {symbol} offen")
    richtung = "LONG" if signal["aktion"] == "BUY" else "SHORT"
    for gruppe in KORRELATIONS_GRUPPEN:
        if symbol in gruppe and any(p["symbol"] in gruppe and p["richtung"] == richtung for p in offene):
            gruende.append("ähnlicher Markt schon in dieselbe Richtung offen (Korrelation)")
    if signal["confidence"] < regeln.min_confidence:
        gruende.append(f"Confidence {signal['confidence']} unter {regeln.min_confidence}")
    if signal["setup"]["crv_netto"] < regeln.min_crv:
        gruende.append(f"CRV nach Kosten {signal['setup']['crv_netto']:.2f} unter {regeln.min_crv}")
    for n in news or []:
        if n.get("waehrung") in NEWS_WAEHRUNGEN.get(symbol, {"USD"}) and \
                abs(n["zeit"] - zeitstempel) <= regeln.news_sperre_minuten * 60:
            gruende.append(f"wichtige News: {n['waehrung']} {n.get('titel', '')}")
            break
    return not gruende, gruende


def positionsgroesse(equity, risiko_prozent, einstieg, stop, kosten, schritt):
    """Einheiten so, dass Stop-Loss + Kosten genau risiko_prozent kosten (abgerundet)."""
    risiko_betrag = equity * risiko_prozent / 100
    abstand = abs(einstieg - stop) + kosten
    if abstand <= 0:
        return 0
    roh = risiko_betrag / abstand
    return int(roh / schritt) * schritt


def tagesbeginn(zeitstempel):
    """Schlüssel des Handelstags (österreichische Zeit)."""
    return wien_zeit(zeitstempel).strftime("%Y-%m-%d")


def naechster_tag(zeitstempel):
    return (wien_zeit(zeitstempel) + timedelta(days=1)).strftime("%Y-%m-%d")
