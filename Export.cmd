@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\portable.ps1" -Action Export
if errorlevel 1 echo Export stopped. Keep this window for inspection.
pause
