@echo off
REM Startet das alte Dashboard (oberflaeche.py) - z. B. ein Design, das Jarvis selbst gebaut hat.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python oberflaeche.py %*
pause
