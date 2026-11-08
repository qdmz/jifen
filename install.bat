@echo off
rem ============================================================
rem  Jifen Mall - one click installer (Windows)
rem  Usage:
rem     install.bat                     install with defaults (port 8770)
rem     install.bat --port 8080         custom port
rem     install.bat --host 0.0.0.0      LAN access
rem     install.bat --no-service        skip auto start at logon
rem     install.bat --help              show all options
rem  Docs: docs\INSTALL.md
rem ============================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "PY="

py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"

if not defined PY (
  echo.
  echo [x] Python 3.8+ was not found.
  echo.
  echo     1^) Download from https://www.python.org/downloads/windows/
  echo     2^) During setup TICK "Add python.exe to PATH"
  echo     3^) Close this window, open a NEW one, run install.bat again
  echo.
  pause
  exit /b 1
)

%PY% "%~dp0tools\setup.py" install %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo [x] Installer exited with code %RC%, see messages above.
pause
exit /b %RC%
