@echo off
setlocal

cd /d "%~dp0"

set "PY_CMD="
where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" set "PY_CMD=%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
if not defined PY_CMD if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY_CMD=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY_CMD if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY_CMD=%LocalAppData%\Programs\Python\Python312\python.exe"

if not defined PY_CMD (
  echo [SOOP WebApp] Python executable was not found.
  pause
  exit /b 1
)

echo [SOOP WebApp] Installing dependencies...
call "%PY_CMD%" -m pip install -r requirements_webapp.txt
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Done.
) else (
  echo Install failed with code %EXIT_CODE%.
)
pause

endlocal
