@echo off
rem ============================================================
rem  Jifen Mall - management CLI (Windows)
rem    jifenctl status | start | stop | restart
rem    jifenctl logs [--lines 100] | backup | init
rem    jifenctl passwd [--user admin] [--pwd NEW]
rem    jifenctl uninstall [--purge]
rem    jifenctl doctor
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
  exit /b 1
)

%PY% "%~dp0tools\setup.py" ctl %*
exit /b %ERRORLEVEL%
