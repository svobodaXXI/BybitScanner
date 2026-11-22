@echo off
setlocal EnableExtensions
title BybitScanner - Mashina Vremeni (LOCAL SIMULATION)
cd /d "%~dp0"

rem Versioned private analytical environment, shared only by Machine Time.
rem The helper verifies imports; missing/broken dependencies fall back to viewer.
set "WEDGE_PY="
where py >nul 2>nul
if errorlevel 1 goto :viewer
for /f "delims=" %%P in ('py -3.11 -B "research\local_replay_viewer\launch_environment.py"') do set "WEDGE_PY=%%P"
if not defined WEDGE_PY goto :viewer
if not exist "%WEDGE_PY%" goto :viewer
if exist "protocol_launcher.py" "%WEDGE_PY%" -B protocol_launcher.py --register >nul 2>nul
if exist "launch_bridge_agent.py" "%WEDGE_PY%" -B launch_bridge_agent.py --install-if-configured >nul 2>nul
"%WEDGE_PY%" -B server.py --port 48765
if errorlevel 1 pause
goto :end

:viewer
where py >nul 2>nul
if not errorlevel 1 (
  if exist "protocol_launcher.py" py -3 -B protocol_launcher.py --register >nul 2>nul
  if exist "launch_bridge_agent.py" py -3 -B launch_bridge_agent.py --install-if-configured >nul 2>nul
  py -3 -B server.py --port 48765
  if errorlevel 1 pause
  goto :end
)
where python >nul 2>nul
if not errorlevel 1 (
  if exist "protocol_launcher.py" python -B protocol_launcher.py --register >nul 2>nul
  if exist "launch_bridge_agent.py" python -B launch_bridge_agent.py --install-if-configured >nul 2>nul
  python -B server.py --port 48765
  if errorlevel 1 pause
  goto :end
)
echo Python 3 is not available on this Windows machine.
echo Install Python 3.11+ and open START_LOCAL.cmd again.
pause
:end
endlocal
