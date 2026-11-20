@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Setup.ps1"
set "CTRLTEA_EXIT=%ERRORLEVEL%"
if not "%CTRLTEA_EXIT%"=="0" echo Installation failed. Read the message above.
pause
exit /b %CTRLTEA_EXIT%
