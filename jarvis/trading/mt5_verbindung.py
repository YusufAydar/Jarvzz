"""
Verbindung zu MetaTrader 5 (z. B. dein FTMO-Konto).

Voraussetzungen:
- MetaTrader 5 ist auf dem PC installiert und mit deinem FTMO-Konto angemeldet
  (oder die Zugangsdaten stehen in jarvis/.env, siehe README).
- Das Python-Paket "MetaTrader5" ist installiert (macht aktualisieren.bat).

In dieser Phase wird NUR gelesen: Kurse, Kerzen, Kontostand, offene Positionen.
Es werden keine Orders geschickt.
"""

import json
import os
import threading
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # sehr alte Python-Versionen
    ZoneInfo = None

import einstellungen

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

ZEITRAHMEN = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
_sperre = threading.Lock()  # MT5 mag keine gleichzeitigen Zugriffe aus mehreren Threads
_symbol_cache = {}


class MT5Fehler(Exception):
    pass


def verbinden():
    """Stellt die Verbindung zum laufenden MetaTrader 5 her (falls noch nicht geschehen)."""
    if not einstellungen.MT5_AKTIV:
        raise MT5Fehler("MetaTrader 5 ist in den Einstellungen ausgeschaltet (MT5_AKTIV = False).")
    if mt5 is None:
        raise MT5Fehler("Das Paket MetaTrader5 fehlt. Bitte aktualisieren.bat ausführen (nur unter Windows).")
    if mt5.terminal_info() is not None:
        return
    # MT5 nie selbst starten – nur verbinden, wenn du es schon geöffnet hast
    if not einstellungen.MT5_AUTOMATISCH_STARTEN and not mt5_laeuft():
        raise MT5Fehler("MetaTrader 5 ist nicht geöffnet. Öffne MT5 und melde dich an, dann klappt es.")
    # Höchstens 15 Sekunden auf MT5 warten, damit Jarvis nicht hängen bleibt
    parameter = {"timeout": 15000}
    login = os.environ.get("MT5_LOGIN")
    if login:
        parameter.update({"login": int(login), "password": os.environ.get("MT5_PASSWORT", ""),
                          "server": os.environ.get("MT5_SERVER", "")})
    if not mt5.initialize(**parameter):
        raise MT5Fehler(f"Keine Verbindung zu MetaTrader 5 ({mt5.last_error()}). "
                        "Ist MT5 geöffnet und mit deinem Konto angemeldet?")


def mt5_laeuft():
    """Prüft, ob das MetaTrader-5-Programm (terminal64.exe) gerade läuft."""
    try:
        import psutil
        return any((p.info["name"] or "").lower() in ("terminal64.exe", "terminal.exe")
                   for p in psutil.process_iter(["name"]))
    except Exception:
        return False


def neu_verbinden():
    """Trennt die Verbindung, damit beim nächsten Zugriff mit den neuen Zugangsdaten angemeldet wird."""
    if mt5 is not None:
        with _sperre:
            mt5.shutdown()
        _symbol_cache.clear()


def symbol_finden(name):
    """
    Findet den genauen Symbolnamen beim Broker. Bei FTMO heißen Indizes z. B. "US30.cash".
    Aus "us30" oder "Dow" wird so das richtige Symbol.
    """
    schluessel = name.upper().strip()
    if schluessel in _symbol_cache:
        return _symbol_cache[schluessel]
    alias = {"DOW": "US30", "DOW JONES": "US30", "NASDAQ": "US100", "NAS100": "US100", "DAX": "GER40",
             "GOLD": "XAUUSD", "SILBER": "XAGUSD", "BITCOIN": "BTCUSD", "ETHEREUM": "ETHUSD",
             "S&P": "US500", "SP500": "US500", "ÖL": "USOIL", "OEL": "USOIL"}
    gesucht = alias.get(schluessel, schluessel).replace("/", "")
    if mt5.symbol_select(gesucht, True):
        _symbol_cache[schluessel] = gesucht
        return gesucht
    kandidaten = [s.name for s in (mt5.symbols_get(f"*{gesucht}*") or [])]
    if not kandidaten:
        raise MT5Fehler(f"Symbol '{name}' gibt es bei deinem Broker nicht.")
    # Bevorzugt: beginnt mit dem Suchbegriff, dann der kürzeste Name
    kandidaten.sort(key=lambda n: (not n.upper().startswith(gesucht), len(n)))
    mt5.symbol_select(kandidaten[0], True)
    _symbol_cache[schluessel] = kandidaten[0]
    return kandidaten[0]


def kerzen(symbol, zeitrahmen="M15", anzahl=300):
    """Holt die letzten Kerzen als Liste von dicts (ältester zuerst)."""
    zeitrahmen = zeitrahmen.upper()
    if zeitrahmen not in ZEITRAHMEN:
        raise MT5Fehler(f"Unbekannter Zeitrahmen {zeitrahmen}. Möglich: {', '.join(ZEITRAHMEN)}")
    with _sperre:
        verbinden()
        sym = symbol_finden(symbol)
        daten = mt5.copy_rates_from_pos(sym, getattr(mt5, f"TIMEFRAME_{zeitrahmen}"), 0, anzahl)
    if daten is None or len(daten) == 0:
        raise MT5Fehler(f"Keine Kursdaten für {sym} ({mt5.last_error()}).")
    return sym, [{"zeit": int(d["time"]), "open": float(d["open"]), "high": float(d["high"]),
                  "low": float(d["low"]), "close": float(d["close"])} for d in daten]


def kontrakt_info(name):
    """(Wert von 1,0 Preisbewegung pro Lot in Kontowährung, kleinster Lot-Schritt) aus MT5."""
    with _sperre:
        verbinden()
        sym = symbol_finden(name)
        info = mt5.symbol_info(sym)
    if info is None or not info.trade_tick_size:
        raise MT5Fehler(f"Keine Kontraktdaten für {sym}.")
    return info.trade_tick_value / info.trade_tick_size, info.volume_step


def nachkommastellen(symbol):
    with _sperre:
        info = mt5.symbol_info(symbol)
    return info.digits if info else 5


def kontostand():
    """Kontostand, Equity und offene Positionen."""
    with _sperre:
        verbinden()
        konto = mt5.account_info()
        positionen = mt5.positions_get() or []
    if konto is None:
        raise MT5Fehler("Kontodaten nicht verfügbar.")
    return {
        "login": konto.login, "server": konto.server, "waehrung": konto.currency,
        "balance": konto.balance, "equity": konto.equity, "gewinn_offen": konto.profit,
        "positionen": [{"symbol": p.symbol, "richtung": "Kauf" if p.type == 0 else "Verkauf",
                        "volumen": p.volume, "einstieg": p.price_open, "sl": p.sl, "tp": p.tp,
                        "gewinn": p.profit} for p in positionen],
    }


# ---------------------------------------------------------------------------
# FTMO-Grenzen
# ---------------------------------------------------------------------------

def _ftmo_heute():
    """FTMO setzt den Tagesverlust um Mitternacht Prager Zeit zurück."""
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("Europe/Prague")).date().isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).date().isoformat()


def tagesstart_balance(balance, datei=None):
    """
    Merkt sich den Kontostand beim ersten Blick an jedem Tag.
    Davon aus wird der Tagesverlust gerechnet.
    """
    datei = datei or (einstellungen.DATEN_ORDNER / "tagesstart.json")
    heute = _ftmo_heute()
    try:
        gespeichert = json.loads(datei.read_text(encoding="utf-8"))
    except Exception:
        gespeichert = {}
    if gespeichert.get("tag") != heute:
        gespeichert = {"tag": heute, "balance": balance}
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text(json.dumps(gespeichert), encoding="utf-8")
    return gespeichert["balance"]


def ftmo_pruefung(konto, start_heute, kontogroesse):
    """
    Vergleicht den Kontostand mit den FTMO-Grenzen und den eigenen, strengeren Sicherheitsgrenzen.
    Gibt ein dict mit allen Zahlen und einer Ampel ("grün", "gelb", "rot") zurück.
    """
    equity = konto["equity"]
    tag_grenze = kontogroesse * einstellungen.FTMO_MAX_TAGESVERLUST / 100
    gesamt_grenze = kontogroesse * einstellungen.FTMO_MAX_GESAMTVERLUST / 100
    tag_sicher = kontogroesse * einstellungen.SICHERHEIT_TAGESVERLUST / 100
    verlust_heute = max(start_heute - equity, 0)
    verlust_gesamt = max(kontogroesse - equity, 0)
    ziel = kontogroesse * (1 + einstellungen.FTMO_GEWINNZIEL / 100)
    if verlust_heute >= tag_sicher or verlust_gesamt >= gesamt_grenze * 0.8:
        ampel = "rot"
    elif verlust_heute >= tag_sicher * 0.6 or verlust_gesamt >= gesamt_grenze * 0.5:
        ampel = "gelb"
    else:
        ampel = "grün"
    return {
        "ampel": ampel,
        "gewinn_heute": equity - start_heute,
        "rest_tagesverlust_ftmo": tag_grenze - verlust_heute,
        "rest_tagesverlust_sicher": tag_sicher - verlust_heute,
        "rest_gesamtverlust": gesamt_grenze - verlust_gesamt,
        "bis_ziel": ziel - equity,
        "fortschritt_ziel_prozent": (equity - kontogroesse) / (ziel - kontogroesse) * 100,
    }
