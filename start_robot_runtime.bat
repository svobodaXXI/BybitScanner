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

set "BYBITSCANNER_PYTHON=%~dp0venv\Scripts\python.exe"

start "BybitScanner - PAPER Backend" powershell.exe -NoExit -Command "Set-Location '%~dp0'; & '%~dp0start_paper_backend.bat'"

timeout /t 2 /nobreak >nul

start "BybitScanner - Telegram Monitoring" powershell.exe -NoExit -Command "Set-Location '%~dp0'; & '%BYBITSCANNER_PYTHON%' '%~dp0telegram_monitoring.py'"

timeout /t 2 /nobreak >nul

powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; $backendUrl = $env:BYBITSCANNER_PAPER_BACKEND_URL; if (-not $backendUrl) { $backendUrl = 'http://127.0.0.1:8765' }; Invoke-RestMethod -Method Post -Uri ($backendUrl.TrimEnd('/') + '/api/scanner/start') -ContentType 'application/json' -Body '{}'"
if errorlevel 1 exit /b 1

exit /b 0
