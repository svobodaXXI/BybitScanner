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
rem No argument means ALL, the full one-action PAPER runtime (Robot + Scanner). The Zapusk robota
rem desktop shortcut passes ALL explicitly and does not depend on this default; SCANNER and ROBOT are explicit.
set "BYBITSCANNER_RUNTIME_INTENT=%~1"
if "%BYBITSCANNER_RUNTIME_INTENT%"=="" set "BYBITSCANNER_RUNTIME_INTENT=ALL"

"%~dp0venv\Scripts\python.exe" -m tools.runtime_intent "%BYBITSCANNER_RUNTIME_INTENT%"
exit /b %errorlevel%
