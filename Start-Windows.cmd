@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run Install-Windows.cmd first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" scripts\start.py --open-browser
set "CTRLTEA_EXIT=%ERRORLEVEL%"
if not "%CTRLTEA_EXIT%"=="0" pause
exit /b %CTRLTEA_EXIT%
