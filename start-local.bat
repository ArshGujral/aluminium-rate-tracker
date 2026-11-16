@echo off
rem Runs the Aluminium Rate Tracker on this computer. Double-click to start; close this window to stop.
cd /d "%~dp0"
title Aluminium Rate Tracker (local)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this again.
  pause
  exit /b 1
)

echo Getting the latest saved rates from the website...
curl -s -f -o data.new https://arshgujral.github.io/aluminium-rate-tracker/data.json
if not errorlevel 1 (move /y data.new data.json >nul) else (if exist data.new del data.new)

echo Checking the MCX rate right now...
python scripts\update_rates.py

echo.
echo Opening http://localhost:8765/  -  keep this window open while you use the tracker.
start "" http://localhost:8765/
python -m http.server 8765 --bind 127.0.0.1
