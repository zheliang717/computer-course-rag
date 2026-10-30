@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\portable.ps1" -Action Import
if errorlevel 1 echo Import stopped. Keep this window and package for inspection.
pause
