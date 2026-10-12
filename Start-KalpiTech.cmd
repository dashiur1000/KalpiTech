@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-KalpiTech.ps1"
exit /b %ERRORLEVEL%
