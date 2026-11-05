"""
Speichert alle Daten lokal in einer SQLite-Datenbank.

SQLite ist eine Datenbank in einer einzigen Datei (daten/hyperliquid.db).
Du brauchst dafür kein extra Programm – Python bringt alles mit.
"""

import sqlite3
import time
from pathlib import Path

TABELLEN = """
CREATE TABLE IF NOT EXISTS trader (
    wallet        TEXT PRIMARY KEY,
    name          TEXT,
    rang          INTEGER,
    aktuell_top   INTEGER DEFAULT 0,   -- 1 = gehört bei der letzten Auswahl zu den Top
    kontowert     REAL,
    pnl_tag       REAL,
    pnl_woche     REAL,
    pnl_monat     REAL,
    pnl_gesamt    REAL,
    roi_monat     REAL,
    volumen_monat REAL,
    aktualisiert  INTEGER               -- Zeitpunkt in Millisekunden
);

CREATE TABLE IF NOT EXISTS fills (
    wallet          TEXT,
    tid             INTEGER,            -- Trade-ID von Hyperliquid
    oid             INTEGER,            -- Order-ID
    coin            TEXT,
    preis           REAL,
    menge           REAL,
    seite           TEXT,               -- "B" = Kauf, "A" = Verkauf
    zeit            INTEGER,            -- Zeitpunkt in Millisekunden
    start_position  REAL,               -- Positionsgröße VOR diesem Trade
    richtung        TEXT,               -- z. B. "Open Long", "Close Short"
    closed_pnl      REAL,               -- realisierter Gewinn/Verlust
    gebuehr         REAL,
    hash            TEXT,
    PRIMARY KEY (wallet, tid, oid)
);
CREATE INDEX IF NOT EXISTS fills_zeit ON fills (zeit);

CREATE TABLE IF NOT EXISTS positionen (
    wallet          TEXT,
    coin            TEXT,
    groesse         REAL,
    einstiegspreis  REAL,
    positionswert   REAL,
    hebel           REAL,
    hebel_typ       TEXT,
    unrealisiert    REAL,
    aktualisiert    INTEGER,
    PRIMARY KEY (wallet, coin)
);
"""


def verbinden(datei):
    """Öffnet die Datenbank (und legt sie an, falls es sie noch nicht gibt)."""
    Path(datei).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(datei)
    db.row_factory = sqlite3.Row  # Ergebnisse lassen sich dann per Spaltenname lesen
    db.executescript(TABELLEN)
    return db


def speichere_top_trader(db, top_liste):
    """Speichert die aktuelle Top-Liste. Alte Top-Trader werden als 'nicht mehr Top' markiert."""
    jetzt = int(time.time() * 1000)
    db.execute("UPDATE trader SET aktuell_top = 0")
    for t in top_liste:
        db.execute(
            """INSERT INTO trader (wallet, name, rang, aktuell_top, kontowert, pnl_tag,
                   pnl_woche, pnl_monat, pnl_gesamt, roi_monat, volumen_monat, aktualisiert)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(wallet) DO UPDATE SET
                   name=excluded.name, rang=excluded.rang, aktuell_top=1,
                   kontowert=excluded.kontowert, pnl_tag=excluded.pnl_tag,
                   pnl_woche=excluded.pnl_woche, pnl_monat=excluded.pnl_monat,
                   pnl_gesamt=excluded.pnl_gesamt, roi_monat=excluded.roi_monat,
                   volumen_monat=excluded.volumen_monat, aktualisiert=excluded.aktualisiert""",
            (t["wallet"], t["name"], t["rang"], t["kontowert"], t["pnl_tag"],
             t["pnl_woche"], t["pnl_monat"], t["pnl_gesamt"], t["roi_monat"],
             t["volumen_monat"], jetzt),
        )
    db.commit()


def letzter_fill_zeitpunkt(db, wallet):
    """Zeitpunkt des neuesten gespeicherten Trades – ab da wird beim nächsten Mal weitergeladen."""
    zeile = db.execute("SELECT MAX(zeit) FROM fills WHERE wallet = ?", (wallet,)).fetchone()
    return zeile[0] or 0


def speichere_fills(db, wallet, fills):
    """Speichert Trades. Trades, die schon da sind, werden einfach übersprungen."""
    vorher = db.total_changes
    db.executemany(
        """INSERT OR IGNORE INTO fills (wallet, tid, oid, coin, preis, menge, seite, zeit,
               start_position, richtung, closed_pnl, gebuehr, hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(wallet, f.get("tid"), f.get("oid"), f.get("coin"), float(f.get("px", 0)),
          float(f.get("sz", 0)), f.get("side"), f.get("time"),
          float(f.get("startPosition") or 0), f.get("dir"),
          float(f.get("closedPnl") or 0), float(f.get("fee") or 0), f.get("hash"))
         for f in fills],
    )
    db.commit()
    return db.total_changes - vorher  # Anzahl wirklich neuer Trades


def speichere_positionen(db, wallet, positionen):
    """Ersetzt die gespeicherten offenen Positionen einer Wallet durch die aktuellen."""
    jetzt = int(time.time() * 1000)
    db.execute("DELETE FROM positionen WHERE wallet = ?", (wallet,))
    db.executemany(
        """INSERT INTO positionen (wallet, coin, groesse, einstiegspreis, positionswert,
               hebel, hebel_typ, unrealisiert, aktualisiert)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(wallet, p["coin"], p["groesse"], p["einstiegspreis"], p["positionswert"],
          p["hebel"], p["hebel_typ"], p["unrealisiert"], jetzt) for p in positionen],
    )
    db.commit()


def aktualisiere_kontowert(db, wallet, kontowert):
    db.execute("UPDATE trader SET kontowert = ? WHERE wallet = ?", (kontowert, wallet))
    db.commit()


def top_trader(db):
    """Alle Trader der aktuellen Top-Liste, sortiert nach Rang."""
    return [dict(z) for z in db.execute(
        "SELECT * FROM trader WHERE aktuell_top = 1 ORDER BY rang")]


def fills_von(db, wallet, ab_zeit=0):
    """Alle gespeicherten Trades einer Wallet, ältester zuerst."""
    return [dict(z) for z in db.execute(
        "SELECT * FROM fills WHERE wallet = ? AND zeit >= ? ORDER BY zeit, tid",
        (wallet, ab_zeit))]


def positionen_von(db, wallet):
    return [dict(z) for z in db.execute(
        "SELECT * FROM positionen WHERE wallet = ?", (wallet,))]
