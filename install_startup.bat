@echo off
title Install Auto-Startup
cd /d "%~dp0"
echo Registering Radar EW Inventory System to Windows Startup...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$s = $ws.CreateShortcut([Environment]::GetFolderPath('Startup') + '\Radar_EW_Inventory_App.lnk'); " ^
  "$s.TargetPath = 'wscript.exe'; " ^
  "$s.Arguments = '\"' + '%~dp0run_background.vbs' + '\"'; " ^
  "$s.WorkingDirectory = '%~dp0'; " ^
  "$s.Description = 'Radar EW Inventory System Auto-Startup'; " ^
  "$s.Save()"

if %errorlevel% equ 0 (
    echo ========================================================
    echo   [SUCCESS] App registered to Windows Startup!
    echo   It will now automatically launch when your PC boots.
    echo ========================================================
) else (
    echo [ERROR] Failed to create startup shortcut.
)
pause
