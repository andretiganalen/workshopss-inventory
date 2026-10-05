@echo off
cd /d "%~dp0"
title Radar EW Facility Workshop Inventory System (Auto-Restart Mode)
echo ========================================================
echo   Launching Persistent Handler (Auto-Restart Enabled)
echo   Target URL: http://127.0.0.1:8000
echo   To stop: Close this window or press Ctrl+C
echo ========================================================

:: Open browser
start "" http://127.0.0.1:8000

:: Launch supervisor
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" server_handler.py
) else (
    python server_handler.py
)
pause
