@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0start_runtime.local.bat" call "%~dp0start_runtime.local.bat"
if errorlevel 1 (
    echo Failed to load start_runtime.local.bat.
    exit /b 1
)

if not exist "%~dp0venv\Scripts\python.exe" (
    echo Python venv not found: %~dp0venv\Scripts\python.exe
    exit /b 1
)

"%~dp0venv\Scripts\python.exe" "%~dp0tools\stop_robot_runtime.py"
exit /b %errorlevel%
