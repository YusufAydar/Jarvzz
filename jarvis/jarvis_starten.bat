@echo off
REM Startet Jarvis. Doppelklicken zum Starten.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python jarvis.py %*
pause
