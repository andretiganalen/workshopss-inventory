@echo off
title Stop Inventory System
echo Stopping processes running on port 8000 and Python handlers...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a 2>nul
)
wmic process where "CommandLine like '%%server_handler.py%%'" call terminate >nul 2>&1
echo Done! App has been stopped.
pause
