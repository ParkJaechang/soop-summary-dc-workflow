@echo off
setlocal

cd /d "%~dp0"

set "SOOP_SERVER_HOST=0.0.0.0"
set "SOOP_OPEN_BROWSER=0"

if "%SOOP_SERVER_PORT%"=="" set "SOOP_SERVER_PORT=8765"

call "%~dp0run_webapp.bat"

endlocal
