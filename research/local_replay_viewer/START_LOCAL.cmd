@echo off
setlocal
title BybitScanner - Mashina Vremeni (LOCAL SIMULATION)
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -B server.py
  if errorlevel 1 pause
  goto :end
)

where python >nul 2>nul
if not errorlevel 1 (
  python -B server.py
  if errorlevel 1 pause
  goto :end
)

echo Python 3 is not available on this Windows machine.
echo Install Python 3.11+ and open START_LOCAL.cmd again.
pause
:end
endlocal
