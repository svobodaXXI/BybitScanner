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

rem Owner intent only; bootstrap, identity and state routing live in tools.runtime_intent.
rem No argument means ROBOT only (the Zapusk robota desktop button); SCANNER and ALL must be explicit.
set "BYBITSCANNER_RUNTIME_INTENT=%~1"
if "%BYBITSCANNER_RUNTIME_INTENT%"=="" set "BYBITSCANNER_RUNTIME_INTENT=ROBOT"

"%~dp0venv\Scripts\python.exe" -m tools.runtime_intent "%BYBITSCANNER_RUNTIME_INTENT%"
exit /b %errorlevel%
