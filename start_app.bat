@echo off
cd /d "%~dp0"
title Radar EW Facility Workshop Inventory System
echo ========================================================
echo   Launching Radar EW Facility Workshop Inventory System
echo   URL: http://127.0.0.1:8000
echo ========================================================

:: Open browser automatically
start "" http://127.0.0.1:8000

:: Use virtual environment if available
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
) else (
    python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
)
pause

