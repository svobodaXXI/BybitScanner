@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0start_runtime.local.bat" call "%~dp0start_runtime.local.bat"
if errorlevel 1 (
    echo Failed to load start_runtime.local.bat.
    pause
    exit /b 1
)

if not exist "%~dp0venv\Scripts\python.exe" (
    echo Python venv not found: %~dp0venv\Scripts\python.exe
    pause
    exit /b 1
)

rem VPS-first route is explicitly selected by machine-local configuration.
rem No local fallback after an unreachable/blocked VPS: it may still own positions.
if defined BYBITSCANNER_VPS_SSH_TARGET (
    if /i "%~1"=="" goto vpsstart
    if /i "%~1"=="ALL" goto vpsstart
)
goto localintent

:vpsstart
"%~dp0venv\Scripts\python.exe" -m tools.vps_owner_launcher
exit /b %errorlevel%

:localintent
rem Legacy local routing remains unchanged until the owner opts into VPS target.
rem Owner intent only; bootstrap, identity and state routing live in tools.runtime_intent.
set "BYBITSCANNER_RUNTIME_INTENT=%~1"
if "%BYBITSCANNER_RUNTIME_INTENT%"=="" set "BYBITSCANNER_RUNTIME_INTENT=ALL"

"%~dp0venv\Scripts\python.exe" -m tools.runtime_intent "%BYBITSCANNER_RUNTIME_INTENT%"
exit /b %errorlevel%
