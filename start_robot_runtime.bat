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
rem Expected PAPER DB identity: SQLiteStore.database_identity for this launcher's DB path.
set "BYBITSCANNER_PAPER_DB_IDENTITY_CODE=import hashlib, os, pathlib; path = pathlib.Path(os.environ.get('BYBITSCANNER_PAPER_DB', 'paper_runtime.sqlite3')); print(hashlib.sha256(str(path.resolve()).encode('utf-8')).hexdigest())"

rem Reuse only a canonical PAPER backend proven for this DB; never start over another listener.
call :probe_paper_backend 0
if errorlevel 2 (
    echo PAPER backend URL answered without matching identity; nothing was started.
    exit /b 1
)
if not errorlevel 1 goto paper_backend_ready

start "BybitScanner - PAPER Backend" powershell.exe -NoExit -Command "Set-Location '%~dp0'; & '%~dp0start_paper_backend.bat'"

rem The spawned backend must prove canonical READY for this DB within the bound.
call :probe_paper_backend 60
if errorlevel 1 (
    echo PAPER backend did not prove READY; Telegram and Scanner were not started.
    exit /b 1
)

:paper_backend_ready
rem Scanner start requires a READY Telegram callback worker; reuse one if present.
call :wait_telegram_ready 1
if errorlevel 2 (
    echo Telegram monitoring is READY for a different PAPER DB; nothing was started.
    exit /b 1
)
if not errorlevel 1 goto telegram_ready

start "BybitScanner - Telegram Monitoring" powershell.exe -NoExit -Command "Set-Location '%~dp0'; & '%BYBITSCANNER_PYTHON%' '%~dp0telegram_monitoring.py'"

call :wait_telegram_ready 60
if errorlevel 1 (
    echo Telegram monitoring is not READY; Scanner was not started.
    exit /b 1
)

rem Route by durable Scanner state; unknown or unavailable state fails closed.
:telegram_ready
rem Robot must accept candidates and protection must be healthy before any Scanner change.
call :probe_paper_backend 0 robot
if errorlevel 1 (
    echo Robot admission or protection is not READY; Scanner was not changed.
    exit /b 1
)
powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; $backendUrl = $env:BYBITSCANNER_PAPER_BACKEND_URL; if (-not $backendUrl) { $backendUrl = 'http://127.0.0.1:8765' }; $base = $backendUrl.TrimEnd('/'); $status = Invoke-RestMethod -Method Get -Uri ($base + '/api/scanner/status'); $mode = if ($status.ok -eq $true) { [string]$status.mode } else { '' }; if ($mode -ceq 'SCANNER_STOPPED') { Invoke-RestMethod -Method Post -Uri ($base + '/api/scanner/start') -ContentType 'application/json' -Body '{}' | Out-Null } elseif ($mode -ceq 'SCANNER_PAUSED') { Invoke-RestMethod -Method Post -Uri ($base + '/api/scanner/resume') -ContentType 'application/json' -Body '{}' | Out-Null } elseif ($mode -ceq 'SCANNER_RUNNING') { Write-Host 'Scanner already running; no lifecycle change.' } else { Write-Host ('Scanner state unknown: ' + $mode); exit 1 }"
if errorlevel 1 exit /b 1

exit /b 0

:wait_telegram_ready
set "BYBITSCANNER_TELEGRAM_WAIT_SECONDS=%~1"
powershell.exe -NoProfile -Command "$port = $env:BYBITSCANNER_TELEGRAM_MONITORING_PORT; if (-not $port) { $port = '8766' }; $deadline = (Get-Date).AddSeconds([int]$env:BYBITSCANNER_TELEGRAM_WAIT_SECONDS); try { $expected = (& $env:BYBITSCANNER_PYTHON -c $env:BYBITSCANNER_PAPER_DB_IDENTITY_CODE | Out-String).Trim() } catch { $expected = '' }; if ($LASTEXITCODE -ne 0 -or $expected -cnotmatch '^[0-9a-f]{64}$') { Write-Host 'Cannot compute PAPER database identity.'; exit 2 }; do { $h = $null; try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri ('http://127.0.0.1:' + $port + '/health'); $h = $r.Content | ConvertFrom-Json } catch {}; if ($h -ne $null -and $r.StatusCode -eq 200 -and $h.component -eq 'telegram_monitoring' -and $h.status -eq 'ready') { if ($h.database_identity -is [string] -and $h.database_identity -ceq $expected) { exit 0 }; Write-Host 'Telegram monitoring is READY for a different or unproven PAPER DB.'; exit 2 }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
exit /b %errorlevel%

:probe_paper_backend
set "BYBITSCANNER_PAPER_BACKEND_WAIT_SECONDS=%~1"
set "BYBITSCANNER_PAPER_BACKEND_REQUIRE=%~2"
powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; $backendUrl = $env:BYBITSCANNER_PAPER_BACKEND_URL; if (-not $backendUrl) { $backendUrl = 'http://127.0.0.1:8765' }; $wait = [int]$env:BYBITSCANNER_PAPER_BACKEND_WAIT_SECONDS; $deadline = (Get-Date).AddSeconds($wait); $requestTimeout = if ($wait -gt 0) { 2 } else { 10 }; $retryable = @('ConnectFailure', 'Timeout', 'ConnectionClosed', 'ReceiveFailure', 'KeepAliveFailure', 'SendFailure'); try { $expected = (& $env:BYBITSCANNER_PYTHON -c $env:BYBITSCANNER_PAPER_DB_IDENTITY_CODE | Out-String).Trim() } catch { $expected = '' }; if ($LASTEXITCODE -ne 0 -or $expected -cnotmatch '^[0-9a-f]{64}$') { Write-Host 'Cannot compute PAPER database identity.'; exit 2 }; do { $r = $null; try { $r = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -TimeoutSec $requestTimeout -Uri ($backendUrl.TrimEnd('/') + '/api/health') } catch [System.Net.WebException] { $status = [string]$_.Exception.Status; if ($_.Exception.Response -ne $null) { Write-Host ('PAPER backend URL answered without proven health: ' + $status); exit 2 }; if ($wait -le 0) { if ($status -eq 'ConnectFailure') { exit 1 }; Write-Host ('PAPER backend URL answered without proven health: ' + $status); exit 2 }; if ($retryable -notcontains $status) { Write-Host ('PAPER backend health probe failed: ' + $status); exit 2 } } catch { Write-Host 'PAPER backend health probe failed.'; exit 2 }; if ($r -ne $null) { try { $h = $r.Content | ConvertFrom-Json } catch { $h = $null }; if ($r.StatusCode -eq 200 -and $h.ok -is [bool] -and $h.ok -and $h.component -ceq 'paper_backend' -and $h.mode -ceq 'paper' -and $h.database_identity -ceq $expected) { if ($env:BYBITSCANNER_PAPER_BACKEND_REQUIRE -cne 'robot') { Write-Host 'PAPER backend READY.'; exit 0 }; if (-not ($h.robot_admission_ready -is [bool] -and $h.robot_admission_ready)) { Write-Host 'Robot admission is not READY.'; exit 2 }; try { $pr = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 10 -Uri ($backendUrl.TrimEnd('/') + '/api/robot/protection-health'); $p = $pr.Content | ConvertFrom-Json } catch { Write-Host 'Robot protection health is unavailable.'; exit 2 }; if ($pr.StatusCode -eq 200 -and $p.ok -is [bool] -and $p.ok -and $p.healthy -is [bool] -and $p.healthy -and $p.unhealthy_symbols -is [System.Management.Automation.PSCustomObject] -and @($p.unhealthy_symbols.PSObject.Properties).Count -eq 0) { Write-Host 'Robot admission and protection READY.'; exit 0 }; Write-Host 'Robot protection is not healthy.'; exit 2 }; Write-Host 'PAPER backend URL answered with a different component or database identity.'; exit 2 }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); Write-Host 'PAPER backend did not become READY within the bound.'; exit 1"
exit /b %errorlevel%
