@echo off
setlocal
cd /d "%~dp0"
start "" pythonw "%~dp0watchdog.py"
timeout /t 2 >nul
python "%~dp0watchdog.py" --status
echo Watchdog started (auto restart app.py when it goes down).
pause
