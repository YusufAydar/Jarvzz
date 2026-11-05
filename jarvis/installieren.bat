@echo off
REM Installiert alles, was Jarvis braucht. Einmal doppelklicken reicht.
cd /d "%~dp0"
echo Installiere Jarvis ...
py -3 -m venv .venv || python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.beispiel .env
echo.
echo Fertig! Jetzt die Datei .env mit dem Editor oeffnen und deinen API-Schluessel eintragen.
notepad .env
pause
