@echo off
setlocal EnableExtensions
title BybitScanner - Mashina Vremeni (LOCAL SIMULATION)
cd /d "%~dp0"

rem Standalone native Wedge/Ikigai research on PUBLIC M5 needs only
rem the shipped offline analytical wheelhouse, not a PAPER account or M1
rem trading manifest. All packages install inside this release's private venv.
rem Actual virtual trading remains separately gated by verified M1 + risk.
if not exist "python-wheels\" goto :viewer
where py >nul 2>nul
if errorlevel 1 goto :viewer
py -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)" >nul 2>nul
if errorlevel 1 goto :viewer

if not exist ".wedge-python\Scripts\python.exe" (
  py -3.11 -m venv ".wedge-python"
  if errorlevel 1 goto :viewer
)
".wedge-python\Scripts\python.exe" -c "import pandas,numpy; assert pandas.__version__ == '2.2.3' and numpy.__version__ == '2.1.3'" >nul 2>nul
if errorlevel 1 (
  ".wedge-python\Scripts\python.exe" -m pip install --disable-pip-version-check --no-index --find-links="%~dp0python-wheels" "pandas==2.2.3" "numpy==2.1.3"
  if errorlevel 1 goto :viewer
)
".wedge-python\Scripts\python.exe" -B server.py
if errorlevel 1 pause
goto :end

:viewer
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
