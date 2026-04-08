@echo off
setlocal

cd /d "%~dp0"

set "PY_CMD="
where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" set "PY_CMD=%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
if not defined PY_CMD if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY_CMD=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY_CMD if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY_CMD=%LocalAppData%\Programs\Python\Python312\python.exe"

if not defined PY_CMD (
  echo [Symbol Cleaner] Python executable was not found.
  pause
  exit /b 1
)

echo [Symbol Cleaner] Starting local server...
call "%PY_CMD%" symbol_cleaner_app.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [Symbol Cleaner] Server exited with code %EXIT_CODE%.
  pause
)

endlocal
