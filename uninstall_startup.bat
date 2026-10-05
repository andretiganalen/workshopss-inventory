@echo off
title Remove Auto-Startup
echo Removing Radar EW Inventory System from Windows Startup...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = [Environment]::GetFolderPath('Startup') + '\Radar_EW_Inventory_App.lnk'; " ^
  "if (Test-Path $p) { Remove-Item $p -Force; Write-Host '[SUCCESS] Startup shortcut removed.' } else { Write-Host 'No startup shortcut found.' }"

pause
