# Neuigkeiten – was Claude an Jarvis geändert hat

Neueste Einträge stehen oben. Jarvis vergleicht diese Datei mit der auf GitHub: Steht dort ein
Eintrag, den es hier noch nicht gibt, meldet er „Update verfügbar“. Nach dem Update kennt Jarvis
die neuesten Einträge (sie stehen in seiner Grundanweisung).

## 2026-11-07 · Erste 20-Jahres-Ergebnisse, Langzeit-Lauf macht weiter
- Ergebnis 20 Jahre H1 (Gold, Silber, EURUSD, GBPUSD, US30): **keine** Strategie besteht. Trend-Pullback auf Gold
  nur PF 1.04 und im letzten Drittel PF 0.31, Mean-Reversion überall klar im Minus (Drawdown über 50 %).
  Bedeutet: die 2-Jahres-Ergebnisse (Gold PF 1.29) sind noch kein echter Vorteil – weiter nur Paper, nichts umstellen.
- `historie.h1_laden(..., nur_gespeichert=True)`: nur schon gespeicherte Monate benutzen, nichts herunterladen.
- Der Backtest-Lauf schreibt sein Ergebnis nach jedem Markt und holt noch nicht geladene Märkte beim nächsten Lauf nach.

## 2026-11-07 · Langzeit-Test über 20 Jahre, 8 Märkte, 100 Top-Trader
- `historie.h1_laden`: bis zu 20 Jahre Stundenkerzen von Dukascopy (eine Datei pro Monat, wird gespeichert).
- Backtest kann jetzt auch auf H1 rechnen (Einstieg H1, Trend H4) und zeigt das Ergebnis **je Jahr** –
  eine Strategie besteht den Langzeit-Test nur, wenn mindestens 60 % der Jahre im Plus sind.
- Der große Backtest-Lauf testet 8 Märkte über 20 Jahre: Gold, Silber, EURUSD, GBPUSD, US30, US500, US100, DAX –
  dazu weiterhin 2 Jahre Daytrading (M15) mit allen FTMO-Grenzen. Ergebnis mit Rangliste.
- Kosten/Mengen für Silber (XAGUSD), GBPUSD, US500 und DAX (GER40) ergänzt.
- Der tägliche Hyperliquid-Bericht wertet jetzt die **100** besten Trader aus (vorher 10) – die Muster werden belastbarer.

## 2026-11-07 · Telegram, manuelle Paper-Trades, Stop-Management, Muster der Top-Trader
- **Telegram:** Mit `TELEGRAM_TOKEN` und `TELEGRAM_CHAT_ID` in `.env` schickt Jarvis alle Meldungen (Trades, News,
  Tagesbericht) aufs Handy. Der Boss kann vom Handy fragen oder `/status`, `/bericht`, `/pause`, `/weiter` schreiben.
  Nur seine Chat-ID wird angenommen; Freigaben gibt es weiterhin nur am PC. Anleitung im README.
- **Manuelle Paper-Trades** (Wunsch von Jarvis/Boss): Werkzeuge `paper_trade_eroeffnen` und `paper_trade_schliessen`.
  Nur Spielgeld, gleiche Risiko-Grenzen wie der Roboter, als „manuell“ markiert und getrennt von der Roboter-Statistik.
- **Stop-Management:** Trades können den Stop auf Einstand ziehen (Break-even) oder nachziehen (Trailing).
  Einstellbar je Markt mit `TRADER_VARIANTE` (Varianten: basis, breakeven, trailing, london, newyork, …).
  Der 2-Jahres-Backtest testet alle Varianten auf Gold und EURUSD – gewählt wird nach den ersten 2/3 der Daten,
  das letzte Drittel ist die Kontrolle.
- **US100** ist vorerst aus den Roboter-Märkten genommen (im 2-Jahres-Test haben dort alle Strategien verloren).
- **Muster der Top-Trader:** `hyperliquid_bericht` mit `art="muster"` zeigt, wie die besten Hyperliquid-Trader
  handeln (mit/gegen Trend, Pullback/Ausbruch, Uhrzeit, Haltedauer) und was davon Geld bringt. Das sind Ideen für
  eigene Regeln – es wird nichts kopiert.

## 2026-11-06 · Kurs-Download für Backtests robuster
- Dukascopy-Tage, die beim ersten Mal nicht laden, werden am Ende einzeln noch einmal versucht.
- `historie.m15_laden` kann jetzt auch nur mit bereits gespeicherten Tagen arbeiten (ohne Download).

## 2026-11-06 · Vier Profi-Strategien im Vergleich, TradingView-Fehler behoben
- Neu: Der Roboter kennt jetzt vier Strategien – Trend-Pullback (bisher), London-Breakout (Spanne 09–10 Uhr),
  New-York-Breakout (Spanne 15:30–16 Uhr) und Mean-Reversion (Bollinger-Bänder in Seitwärtsphasen).
- Werkzeug `backtest_starten` hat die Option `strategie`: „alle“ vergleicht alle vier auf denselben Kursdaten
  (2 Jahre, mit Kosten) und sortiert sie – bestandene zuerst.
- Einstellung `TRADER_STRATEGIE` legt fest, welche Strategie je Markt im Paper-Konto handelt (Standard: Trend-Pullback).
  Erst umstellen, wenn der Vergleich eine Strategie als BESTANDEN zeigt – und nur nach Rückfrage beim Boss.
- Fehler behoben: Bei lauter VERKAUFEN-Signalen meldete die TradingView-Analyse fälschlich
  „klare Richtung nach oben“ (weil das Wort VERKAUFEN „KAUFEN“ enthält).
- Dukascopy: Die letzten 2 Tage zählen nicht mehr als Ladefehler (werden dort oft erst später bereitgestellt).

## 2026-11-06 · Backtest über 2 Jahre mit Dukascopy-Kursen
backtest_starten lädt jetzt standardmäßig 2 Jahre 15-Minuten-Kerzen von Dukascopy (kostenlos, wird in
daten/historie/ gespeichert, erster Download dauert einige Minuten) und zeigt zusätzlich das Ergebnis je Quartal.
Parameter tage für andere Zeiträume. Fällt Dukascopy aus, wird wie bisher Yahoo/MT5 benutzt.

## 2026-11-06 · Trading-Roboter (Paper-Trading), rotes Farbschema, Unterbrechen beim Sprechen
Neuer Trading-Roboter (Ordner trader/), läuft in der Zentrale mit: beobachtet XAUUSD, US100 und EURUSD jede Minute,
entscheidet bei jeder abgeschlossenen 15-Minuten-Kerze BUY/SELL/HOLD/WAIT mit Begründung und Confidence-Score
(6 nachvollziehbare Teile, noch nicht kalibriert) und handelt nur mit virtuellem Geld (Paper-Trading, Stufe 1,
Konto 10.000 $, Risiko 1 % pro Trade, Tagesstopp 2 %, max. Drawdown 6 %, Handelszeit 09–21 Uhr, News-Sperre,
Korrelations-Sperre, Pause nach 3 Verlusten, Not-Aus). Echte Orders sind gesperrt. Neue Werkzeuge: trader_status,
trader_steuern (pause/fortsetzen/notaus/zuruecksetzen), backtest_starten (mit Kosten, Kalibrierung, Stabilität,
Monte-Carlo und Urteil) und trading_tagesbericht (automatisch um 21 Uhr). In der Zentrale: Feld AUTO-TRADER und
ROBOTER-ENTSCHEIDUNGEN. Übernommen von Jarvis: rotes Farbschema (Einstellung FARBSCHEMA) und das Unterbrechen beim
Sprechen (UNTERBRECHEN), dazu ein STOPP-Knopf in der Zentrale.

## 2026-11-05 · Trading-Zentrale mit Live-TradingView-Chart und Verbindung zu Claude
Neue Oberfläche „Jarvis Trading-Zentrale“ (jarvis_zentrale.bat, auch jarvis_oberflaeche.bat startet sie jetzt):
echter TradingView-Chart in der Mitte (umschaltbar auf den eigenen Jarvis-Chart mit Zonen, Pivots, Positionen),
FTMO-Konto, Watchlist, Setup-Scanner, Positionsrechner, TradingView-Ratings M15/H1/H4/D1, News mit Countdown,
Alarme, Hyperliquid-Profis, Meldungen und Trading-Tagebuch. Neue Werkzeuge: chart_zeigen (Jarvis schaltet den
Chart in der Zentrale um), bildschirm_ansehen (Jarvis sieht sich per Screenshot den Chart des Nutzers an),
tagebuch_eintragen und tagebuch_auswertung, an_claude_melden (eigene Änderungen per GitHub an Claude melden),
neuigkeiten (was ist neu, gibt es ein Update). Wächter im Hintergrund: Warnung 15 Minuten vor wichtigen News,
FTMO-Ampel-Warnung, Erinnerung an offene Positionen am Abend, Update-Hinweis. Das alte Design startet mit
jarvis_altes_design.bat.

## 2026-11-05 · Trading-Werkzeuge: TradingView, Setup-Scanner, Alarme, News, Positionsgröße
tradingview_analyse (TradingView-Ratings über mehrere Zeitrahmen), setup_scanner (regelbasierte Pullback-Setups
mit Einstieg, Stop-Loss, Ziel, CRV), positionsgroesse_berechnen (Lots für festes Risiko), alarm_setzen und
alarme_verwalten (Preis-, RSI- und Setup-Alarme mit Sprachmeldung), wirtschaftskalender (wichtige News).
Kurse für Gold, Forex und Indizes kommen ohne MT5 von Yahoo Finance, Krypto von Hyperliquid.
Der Updater sichert vorher alles und überschreibt keine selbst geänderten Dateien mehr (neue Version als .neu).

## 2026-11-05 · Vollzugriff, eigene Werkzeuge, Auto-Update, MT5-Anbindung
befehl_ausfuehren (PowerShell mit Freigabe), werkzeug_erstellen (Plugins in plugins/), jarvis_aktualisieren,
mt5_zugang_speichern, markt_analyse, maerkte_ueberblick, konto_status (FTMO-Ampel und Grenzen).
MT5 wird nur verbunden, wenn es schon geöffnet ist.
