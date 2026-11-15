@echo off
cd /d "%~dp0"
python -c "import zoneinfo; zoneinfo.ZoneInfo('Europe/Madrid')" >nul 2>&1
if errorlevel 1 python -m pip install --user tzdata
python server.py
