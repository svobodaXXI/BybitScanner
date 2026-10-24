# Read-only owner check. Does not start any runtime or read/write local config files.
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9_.:-]{1,128}$')][string]$SignalId,
    [ValidatePattern('^[A-Z0-9]{2,32}USDT$')][string]$Symbol,
    [int]$BackendPort = 8765,
    [int]$WorkspacePort = 4173
)
$ErrorActionPreference = "Stop"
if ($BackendPort -lt 1024 -or $BackendPort -gt 65535 -or
    $WorkspacePort -lt 1024 -or $WorkspacePort -gt 65535) {
    throw "Invalid local port"
}
$key = [Environment]::GetEnvironmentVariable("BYBITSCANNER_SIGNAL_GEOMETRY_TOKEN")
if ([string]::IsNullOrWhiteSpace($key) -or $key.Trim().Length -lt 32) {
    Write-Host "FAIL: dedicated signal geometry key not present in this PowerShell environment"
    exit 1
}
$operatorKey = [Environment]::GetEnvironmentVariable("BYBITSCANNER_OPERATOR_TOKEN")
if (![string]::IsNullOrWhiteSpace($operatorKey) -and
    $key.Trim() -ceq $operatorKey.Trim()) {
    Write-Host "FAIL: signal geometry key must be distinct from the LIVE operator key"
    Remove-Variable key, operatorKey -ErrorAction SilentlyContinue
    exit 1
}
Remove-Variable operatorKey -ErrorAction SilentlyContinue
Write-Host "PASS: dedicated geometry key present and separate (value hidden)"
if (!$SignalId) {
    Write-Host "No SignalId supplied: remote authorization and archive lookup NOT checked"
    exit 0
}
$encoded = [uri]::EscapeDataString($SignalId)
$relative = "/api/workspace/signal-geometry?signal_id=$encoded"
try {
    $backend = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$BackendPort$relative" -Headers @{
        "X-BybitScanner-Signal-Geometry-Token" = $key.Trim()
    } -TimeoutSec 5
    if (!$backend.ok -or $backend.snapshot.signal_id -ne $SignalId -or
        ($Symbol -and $backend.snapshot.symbol -ne $Symbol)) {
        throw "backend mismatch"
    }
    Write-Host "PASS: backend accepted read-only archive request"
} catch {
    Write-Host "FAIL: backend authorization, archive, or identity unavailable"
    exit 1
} finally {
    Remove-Variable key -ErrorAction SilentlyContinue
}
try {
    $browser = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$WorkspacePort$relative" -TimeoutSec 5
    if (!$browser.ok -or $browser.snapshot.signal_id -ne $SignalId -or
        ($Symbol -and $browser.snapshot.symbol -ne $Symbol)) {
        throw "workspace mismatch"
    }
    Write-Host "PASS: running frontend proxy resolves identical signal identity"
} catch {
    Write-Host "FAIL: frontend proxy credential or archived signal unavailable"
    exit 1
}
Write-Host "PASS: historical EDITOR read path ready for visual acceptance"
