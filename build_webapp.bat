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

echo [SOOP WebApp] Building executable...
call "%PY_CMD%" -m pip install pyinstaller
if errorlevel 1 (
  echo.
  echo [SOOP WebApp] Failed to install PyInstaller.
  pause
  exit /b 1
)

call "%PY_CMD%" -m PyInstaller --noconfirm --clean soop_webapp_v1.spec
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Build finished.
) else (
  echo Build failed with code %EXIT_CODE%.
)
pause

endlocal
