@echo off
powershell.exe -NoProfile -File "%~dp0scripts\open_comparison.ps1"
if errorlevel 1 pause
