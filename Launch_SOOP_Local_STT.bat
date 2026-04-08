@echo off
setlocal

cd /d "C:\python"

set "PY_CMD="
if exist "%LocalAppData%\Python\pythoncore-3.14-64\pythonw.exe" set "PY_CMD=%LocalAppData%\Python\pythoncore-3.14-64\pythonw.exe"
if not defined PY_CMD if exist "%LocalAppData%\Python\bin\pythonw.exe" set "PY_CMD=%LocalAppData%\Python\bin\pythonw.exe"
if not defined PY_CMD if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" set "PY_CMD=%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
if not defined PY_CMD if exist "%LocalAppData%\Python\bin\python.exe" set "PY_CMD=%LocalAppData%\Python\bin\python.exe"
if not defined PY_CMD (
  echo Python executable was not found.
  pause
  exit /b 1
)

start "" "%PY_CMD%" "C:\python\soop_summery_local_v3.py"

endlocal
