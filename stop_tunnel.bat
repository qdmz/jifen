@echo off
rem  Stop the jifen Cloudflare Tunnel (does not remove the logon task).
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY ( exit /b 1 )
%PY% "%~dp0tools\tunnel.py" stop
echo.
pause
exit /b %ERRORLEVEL%
