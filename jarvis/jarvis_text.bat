@echo off
REM Startet Jarvis im Textmodus (tippen statt sprechen).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python jarvis.py --text
pause
