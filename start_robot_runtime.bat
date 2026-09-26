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

rem Scanner start requires a READY Telegram callback worker; reuse one if present.
call :wait_telegram_ready 1
if not errorlevel 1 goto telegram_ready

start "BybitScanner - Telegram Monitoring" powershell.exe -NoExit -Command "Set-Location '%~dp0'; & '%BYBITSCANNER_PYTHON%' '%~dp0telegram_monitoring.py'"

call :wait_telegram_ready 60
if errorlevel 1 (
    echo Telegram monitoring is not READY; Scanner was not started.
    exit /b 1
)

:telegram_ready
powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; $backendUrl = $env:BYBITSCANNER_PAPER_BACKEND_URL; if (-not $backendUrl) { $backendUrl = 'http://127.0.0.1:8765' }; Invoke-RestMethod -Method Post -Uri ($backendUrl.TrimEnd('/') + '/api/scanner/start') -ContentType 'application/json' -Body '{}'"
if errorlevel 1 exit /b 1

exit /b 0

:wait_telegram_ready
set "BYBITSCANNER_TELEGRAM_WAIT_SECONDS=%~1"
powershell.exe -NoProfile -Command "$port = $env:BYBITSCANNER_TELEGRAM_MONITORING_PORT; if (-not $port) { $port = '8766' }; $deadline = (Get-Date).AddSeconds([int]$env:BYBITSCANNER_TELEGRAM_WAIT_SECONDS); do { try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri ('http://127.0.0.1:' + $port + '/health'); if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
exit /b %errorlevel%
