@echo off
REM Startet Jarvis mit Oberflaeche - seit dem Update ist das die TRADING-ZENTRALE.
REM (Das alte Design startest du mit jarvis_altes_design.bat)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python zentrale.py %*
pause
