@echo off
rem ============================================================
rem  Start the Cloudflare Tunnel that publishes the demo site
rem  https://jifen.qdmzctyun.dpdns.org  ->  127.0.0.1:8770
rem  No administrator rights needed. Also registers a logon task
rem  (JifenTunnel) so it comes back after reboot.
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
  echo [x] Python 3.8+ not found in PATH.
  pause
  exit /b 1
)
%PY% "%~dp0tools\tunnel.py" start %*
echo.
pause
exit /b %ERRORLEVEL%
