@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
where pythonw >nul 2>&1
if errorlevel 1 (
  echo [ERROR] pythonw not found in PATH. Install Python 3.8+ and tick "Add to PATH".
  pause
  exit /b 1
)
wscript "%~dp0start_silent.vbs"
timeout /t 2 >nul
python "%~dp0watchdog.py" --status
echo.
echo Admin : http://127.0.0.1:8770/jifen-admin.html
echo Public: http://127.0.0.1:8770/jifen.html
echo Log   : logs\app.log
pause
