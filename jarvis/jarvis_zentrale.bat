@echo off
REM Startet die JARVIS TRADING-ZENTRALE (Live-Chart, Setups, News, Alarme, Konto ...).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python zentrale.py %*
pause
