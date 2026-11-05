@echo off
REM Installiert neue Pakete nach einem Update (dein Schluessel in .env bleibt erhalten).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pip install -r requirements.txt
echo.
echo Fertig!
pause
