"""
Einstellungen für das ganze Projekt.

Hier stehen alle Werte, die du vielleicht einmal ändern möchtest.
Die meisten kannst du auch beim Start überschreiben, z. B.:
    python main.py --anzahl 100
"""

from pathlib import Path

# Ordner, in dem dieses Projekt liegt
PROJEKT_ORDNER = Path(__file__).resolve().parent

# Wie viele Trader sollen analysiert werden? (Klein anfangen: 10)
STANDARD_ANZAHL_TRADER = 10

# Nach welchem Zeitraum wird die Rangliste sortiert?
# Möglich: "day" (Tag), "week" (Woche), "month" (Monat), "allTime" (gesamt)
# "month" nimmt Trader, die AKTUELL gut sind – das passt am besten zum Tagesbericht.
STANDARD_ZEITRAUM = "month"

# Wallets mit weniger Geld auf dem Konto werden übersprungen (in US-Dollar).
# So landen keine "leeren" Wallets in der Auswahl, die gar nicht mehr handeln.
MIN_KONTOWERT = 10_000

# Hier wird die Datenbank gespeichert
DATENBANK_DATEI = PROJEKT_ORDNER / "daten" / "hyperliquid.db"

# Hier landen die täglichen Berichte
BERICHTE_ORDNER = PROJEKT_ORDNER / "berichte"

# Ab wann gilt etwas als "Einigkeit"?
# Mindestens so viele Trader müssen beim Coin aktiv sein ...
EINIGKEIT_MIN_TRADER = 3
# ... und mindestens dieser Anteil muss in dieselbe Richtung handeln (0.7 = 70 %).
EINIGKEIT_MIN_ANTEIL = 0.7

# Pause zwischen zwei API-Anfragen in Sekunden (damit Hyperliquid uns nicht sperrt)
PAUSE_ZWISCHEN_ANFRAGEN = 0.5
