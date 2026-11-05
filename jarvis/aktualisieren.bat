@echo off
REM Holt die neueste Jarvis-Version von GitHub (deine .env, Einstellungen, Termine und Plugins bleiben).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python updater.py
pause
