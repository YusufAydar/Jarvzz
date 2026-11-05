@echo off
REM Startet Jarvis mit Oberflaeche (Dashboard). Doppelklicken zum Starten.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python oberflaeche.py %*
pause
