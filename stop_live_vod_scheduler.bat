@echo off
setlocal

cd /d "%~dp0"

set "PY_CMD="
where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" set "PY_CMD=%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
if not defined PY_CMD if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY_CMD=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY_CMD if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY_CMD=%LocalAppData%\Programs\Python\Python312\python.exe"

if not defined PY_CMD (
  echo [Live VOD Scheduler] Python executable was not found.
  exit /b 1
)

call "%PY_CMD%" live_vod_scheduler_launcher.py stop %*
exit /b %ERRORLEVEL%
