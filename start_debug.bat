@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo Start in foreground (Ctrl+C to stop). Logs also go to logs\app.log
python "%~dp0app.py"
pause
