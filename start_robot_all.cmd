@echo off
setlocal
title BybitScanner - PAPER Robot Launcher
rem Local, untracked desktop wiring behind "Zapusk robota" -> C:\BybitScanner\start_robot.bat.
rem Gates mirror tracked start_robot_runtime.bat (main b51fb16). That launcher cannot be
rem delegated to from this runtime root: it requires %%~dp0venv (absent here) and has no
rem Robot lifecycle step. Every unproven state fails closed; nothing is force-started.

set "ROOT=C:\BybitScanner-box-robot-run"
set "BYBITSCANNER_PYTHON=C:\BybitScanner\venv\Scripts\python.exe"
set "BYBITSCANNER_PAPER_DB=%ROOT%\paper_runtime.sqlite3"
set "BYBITSCANNER_PAPER_BACKEND_URL=http://127.0.0.1:8765"
set "BYBITSCANNER_TELEGRAM_MONITORING_PORT=8766"
set "BYBITSCANNER_IKIGAI_BOX_SIGNALS=1"
set "BYBITSCANNER_IKIGAI_BOX_WATCH=1"
rem LIVE gates stay OFF for every process started from here.
set "LIVE_MARKET_MUTATIONS_ENABLED=false"
set "LIVE_MAINNET_AUTHORIZED=false"
set "LIVE_MARKET_ACCEPTANCE_SINGLE_FLIGHT=false"
set "LIVE_MARKET_ACCEPTANCE_NOTIONAL_CEILING=0"
set "LIVE_PARITY_MUTATIONS_ENABLED=false"
set "LIVE_LIMIT_MUTATIONS_ENABLED=false"
set "LIVE_LIMIT_ACCEPTANCE_NOTIONAL_CEILING=0"
set "BYBITSCANNER_OPERATOR_TOKEN="
rem Expected PAPER DB identity: SQLiteStore.database_identity for this DB path.
set "BYBITSCANNER_PAPER_DB_IDENTITY_CODE=import hashlib, os, pathlib; path = pathlib.Path(os.environ.get('BYBITSCANNER_PAPER_DB', 'paper_runtime.sqlite3')); print(hashlib.sha256(str(path.resolve()).encode('utf-8')).hexdigest())"
rem Robot legal-state routing via terminal.application.robot_control; any other pair,
rem including RECONCILIATION_REQUIRED or a missing runtime row, is rejected unchanged.
set "BYBITSCANNER_ROBOT_ROUTE_CODE=import os, sys; from terminal.application import robot_control as rc; p = os.environ['BYBITSCANNER_PAPER_DB']; r = rc.get_robot_runtime_status(database_path=p); s = None if r is None else (r.mode, r.recovery_status); print('Robot state before:', s); route = {('ROBOT_STOPPED', 'ROBOT_STOPPED'): rc.start_robot, ('ROBOT_RUNNING', 'PAUSED'): rc.resume_robot, ('ROBOT_RUNNING', 'READY'): None}; (s in route) or sys.exit('Robot state is not a legal launch state; Robot was NOT changed.'); r = route[s](database_path=p) if route[s] else r; print('Robot state after:', (r.mode, r.recovery_status)); sys.exit(0 if (r.mode, r.recovery_status) == ('ROBOT_RUNNING', 'READY') else 3)"

cd /d "%ROOT%"
if errorlevel 1 (
    set "FAIL=Runtime root is unavailable; nothing was started."
    goto fail
)
if not exist "%BYBITSCANNER_PYTHON%" (
    set "FAIL=Python venv not found; nothing was started."
    goto fail
)
if not exist "%BYBITSCANNER_PAPER_DB%" (
    set "FAIL=Authoritative PAPER DB not found; nothing was started."
    goto fail
)

rem 1. Reuse only a canonical PAPER backend proven for this DB; an open port is not proof.
call :probe_paper_backend 0
if errorlevel 2 (
    set "FAIL=PAPER backend URL answered without matching identity; nothing was started."
    goto fail
)
if not errorlevel 1 goto paper_backend_ready

start "BybitScanner - PAPER Backend" powershell.exe -NoExit -Command "Set-Location '%ROOT%'; & '%BYBITSCANNER_PYTHON%' -m terminal.runtime.paper_http_server"

call :probe_paper_backend 60
if errorlevel 1 (
    set "FAIL=PAPER backend did not prove READY; Telegram, Robot and Scanner were not changed."
    goto fail
)

:paper_backend_ready
rem 2. Singleton Telegram Monitoring must be READY for this same DB before any Scanner change.
call :wait_telegram_ready 1
if errorlevel 2 (
    set "FAIL=Telegram Monitoring is READY for a different PAPER DB; Robot and Scanner were not changed."
    goto fail
)
if not errorlevel 1 goto telegram_ready

start "BybitScanner - Telegram Monitoring" powershell.exe -NoExit -Command "Set-Location '%ROOT%'; & '%BYBITSCANNER_PYTHON%' '%ROOT%\telegram_monitoring.py'"

call :wait_telegram_ready 60
if errorlevel 1 (
    set "FAIL=Telegram Monitoring is not READY; Robot and Scanner were not changed."
    goto fail
)

:telegram_ready
rem 3. LIVE-off and Scanner acceptance config must be proven before the Robot is changed.
call :probe_paper_backend 0 safe
if errorlevel 1 (
    set "FAIL=Backend PAPER/LIVE safety is not proven; Robot and Scanner were not changed."
    goto fail
)

rem 4. Robot: STOPPED/STOPPED -> start, RUNNING/PAUSED -> resume, RUNNING/READY -> reuse.
"%BYBITSCANNER_PYTHON%" -c "%BYBITSCANNER_ROBOT_ROUTE_CODE%"
if errorlevel 1 (
    set "FAIL=Robot is not RUNNING + READY; Scanner was not changed."
    goto fail
)

rem 5. Identity, PAPER/LIVE safety, Scanner acceptance, Robot admission, protection health.
call :probe_paper_backend 0 robot
if errorlevel 1 (
    set "FAIL=Robot admission or protection is not READY; Scanner was not changed."
    goto fail
)

rem 6. Route Scanner by durable ScannerControlRuntime state; unknown fails closed.
powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; $backendUrl = $env:BYBITSCANNER_PAPER_BACKEND_URL; if (-not $backendUrl) { $backendUrl = 'http://127.0.0.1:8765' }; $base = $backendUrl.TrimEnd('/'); $status = Invoke-RestMethod -Method Get -Uri ($base + '/api/scanner/status'); $mode = if ($status.ok -eq $true) { [string]$status.mode } else { '' }; if ($mode -ceq 'SCANNER_STOPPED') { Invoke-RestMethod -Method Post -Uri ($base + '/api/scanner/start') -ContentType 'application/json' -Body '{}' | Out-Null } elseif ($mode -ceq 'SCANNER_PAUSED') { Invoke-RestMethod -Method Post -Uri ($base + '/api/scanner/resume') -ContentType 'application/json' -Body '{}' | Out-Null } elseif ($mode -ceq 'SCANNER_RUNNING') { Write-Host 'Scanner already running; no lifecycle change.' } else { Write-Host ('Scanner state unknown: ' + $mode); exit 1 }"
if errorlevel 1 (
    set "FAIL=Scanner routing failed; state was not proven."
    goto fail
)

echo.
echo PAPER Robot + Scanner READY on %BYBITSCANNER_PAPER_DB%.
echo LIVE trading remains disabled.
pause
exit /b 0

:fail
echo.
echo ERROR: %FAIL%
echo LIVE trading remains disabled.
pause
exit /b 1

:wait_telegram_ready
set "BYBITSCANNER_TELEGRAM_WAIT_SECONDS=%~1"
powershell.exe -NoProfile -Command "$port = $env:BYBITSCANNER_TELEGRAM_MONITORING_PORT; if (-not $port) { $port = '8766' }; $deadline = (Get-Date).AddSeconds([int]$env:BYBITSCANNER_TELEGRAM_WAIT_SECONDS); try { $expected = (& $env:BYBITSCANNER_PYTHON -c $env:BYBITSCANNER_PAPER_DB_IDENTITY_CODE | Out-String).Trim() } catch { $expected = '' }; if ($LASTEXITCODE -ne 0 -or $expected -cnotmatch '^[0-9a-f]{64}$') { Write-Host 'Cannot compute PAPER database identity.'; exit 2 }; do { $h = $null; try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri ('http://127.0.0.1:' + $port + '/health'); $h = $r.Content | ConvertFrom-Json } catch {}; if ($h -ne $null -and $r.StatusCode -eq 200 -and $h.component -eq 'telegram_monitoring' -and $h.status -eq 'ready') { if ($h.database_identity -is [string] -and $h.database_identity -ceq $expected) { exit 0 }; Write-Host 'Telegram monitoring is READY for a different or unproven PAPER DB.'; exit 2 }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
exit /b %errorlevel%

:probe_paper_backend
rem Args: wait seconds; optional requirement: safe (PAPER/LIVE + Scanner acceptance)
rem or robot (safe + Robot admission + protection health). Exit 0 proven, 1 offline, 2 refused.
set "BYBITSCANNER_PAPER_BACKEND_WAIT_SECONDS=%~1"
set "BYBITSCANNER_PAPER_BACKEND_REQUIRE=%~2"
powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; $backendUrl = $env:BYBITSCANNER_PAPER_BACKEND_URL; if (-not $backendUrl) { $backendUrl = 'http://127.0.0.1:8765' }; $require = [string]$env:BYBITSCANNER_PAPER_BACKEND_REQUIRE; $wait = [int]$env:BYBITSCANNER_PAPER_BACKEND_WAIT_SECONDS; $deadline = (Get-Date).AddSeconds($wait); $requestTimeout = if ($wait -gt 0) { 2 } else { 10 }; $retryable = @('ConnectFailure', 'Timeout', 'ConnectionClosed', 'ReceiveFailure', 'KeepAliveFailure', 'SendFailure'); try { $expected = (& $env:BYBITSCANNER_PYTHON -c $env:BYBITSCANNER_PAPER_DB_IDENTITY_CODE | Out-String).Trim() } catch { $expected = '' }; if ($LASTEXITCODE -ne 0 -or $expected -cnotmatch '^[0-9a-f]{64}$') { Write-Host 'Cannot compute PAPER database identity.'; exit 2 }; do { $r = $null; try { $r = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -TimeoutSec $requestTimeout -Uri ($backendUrl.TrimEnd('/') + '/api/health') } catch [System.Net.WebException] { $status = [string]$_.Exception.Status; if ($_.Exception.Response -ne $null) { Write-Host ('PAPER backend URL answered without proven health: ' + $status); exit 2 }; if ($wait -le 0) { if ($status -eq 'ConnectFailure') { exit 1 }; Write-Host ('PAPER backend URL answered without proven health: ' + $status); exit 2 }; if ($retryable -notcontains $status) { Write-Host ('PAPER backend health probe failed: ' + $status); exit 2 } } catch { Write-Host 'PAPER backend health probe failed.'; exit 2 }; if ($r -ne $null) { try { $h = $r.Content | ConvertFrom-Json } catch { $h = $null }; if ($r.StatusCode -eq 200 -and $h.ok -is [bool] -and $h.ok -and $h.component -ceq 'paper_backend' -and $h.mode -ceq 'paper' -and $h.database_identity -ceq $expected) { if ($require -ceq '') { Write-Host 'PAPER backend READY.'; exit 0 }; if (-not ($h.paper_live_safe -is [bool] -and $h.paper_live_safe -and $h.scanner_acceptance_ready -is [bool] -and $h.scanner_acceptance_ready)) { Write-Host 'Backend PAPER/LIVE safety or Scanner acceptance config is not proven.'; exit 2 }; if ($require -ceq 'safe') { Write-Host 'Backend PAPER/LIVE safety proven.'; exit 0 }; if ($require -cne 'robot') { Write-Host 'Unknown backend requirement.'; exit 2 }; if (-not ($h.robot_admission_ready -is [bool] -and $h.robot_admission_ready)) { Write-Host 'Robot admission is not READY.'; exit 2 }; try { $pr = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 10 -Uri ($backendUrl.TrimEnd('/') + '/api/robot/protection-health'); $p = $pr.Content | ConvertFrom-Json } catch { Write-Host 'Robot protection health is unavailable.'; exit 2 }; if ($pr.StatusCode -eq 200 -and $p.ok -is [bool] -and $p.ok -and $p.healthy -is [bool] -and $p.healthy -and $p.unhealthy_symbols -is [System.Management.Automation.PSCustomObject] -and @($p.unhealthy_symbols.PSObject.Properties).Count -eq 0) { Write-Host 'Robot admission and protection READY.'; exit 0 }; Write-Host 'Robot protection is not healthy.'; exit 2 }; Write-Host 'PAPER backend URL answered with a different component or database identity.'; exit 2 }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); Write-Host 'PAPER backend did not become READY within the bound.'; exit 1"
exit /b %errorlevel%
