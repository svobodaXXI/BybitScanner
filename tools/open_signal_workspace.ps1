[CmdletBinding()]
param(
 [ValidateSet("EDITOR","TERMINAL")][string]$Mode,
 [ValidatePattern('^[A-Z0-9]{2,32}USDT$')][string]$Symbol,
 [ValidateSet("15s","1m","5m","15m","1h","1d")][string]$Timeframe
)
$ErrorActionPreference = "Stop"
$port = 4173
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot "start_workspace_web.ps1"
if (!(Test-Path $launcher)) { throw "Workspace web launcher is missing; integrate PR #582" }
$localUrl = "http://127.0.0.1:$port/?mode=$Mode&symbol=$Symbol&timeframe=$Timeframe"
Write-Host "BybitScanner Workspace: $Mode $Symbol $Timeframe"
Write-Host "PC URL: $localUrl"
Write-Host "Checking local frontend..."
try { $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/" -TimeoutSec 2 } catch { $response = $null }
if (!$response -or $response.StatusCode -ne 200) {
  Write-Host "Starting local frontend; Robot/Scanner will not be started."
  Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-File", ('"' + $launcher + '"'), "-Build") -WorkingDirectory $root
  $deadline = (Get-Date).AddSeconds(90)
  $ready = $false
  do {
    Start-Sleep -Seconds 1
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/" -TimeoutSec 2
      if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
  } while ((Get-Date) -lt $deadline)
  if (!$ready) { throw "Local frontend did not become ready; browser not opened" }
}
Write-Host "READY: $localUrl"
Start-Process $localUrl
Write-Host "Browser opened."
$remoteBase = [Environment]::GetEnvironmentVariable("BYBITSCANNER_TERMINAL_HTTPS_URL")
if ($remoteBase) {
  try {
    $uri = [Uri]$remoteBase
    if ($uri.Scheme -ne "https" -or !$uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.Port -ne 443) {
      throw "Unsafe HTTPS origin"
    }
    $remoteUrl = "$($uri.GetLeftPart([System.UriPartial]::Path).TrimEnd('/'))/?mode=$Mode&symbol=$Symbol&timeframe=$Timeframe"
    Write-Host "Smartphone URL (NOT VERIFIED): $remoteUrl"
    Write-Warning "No mobile QR until HTTPS authentication and gateway readiness are verified."
  } catch {
    Write-Warning "Invalid smartphone HTTPS URL."
  }
} else {
  Write-Host "Smartphone: HTTPS not configured. PC localhost only."
}
$delivery = Join-Path $PSScriptRoot "workspace_ready_delivery.py"
$python = Join-Path $root "venv\Scripts\python.exe"
if ((Test-Path $delivery) -and (Test-Path $python)) {
  Write-Host "Checking local UI and authenticated mobile HTTPS before Telegram QR delivery..."
  & $python $delivery --mode $Mode --symbol $Symbol --timeframe $Timeframe
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "Verified Telegram QR delivery failed. The local PC browser remains open."
  }
}
Read-Host "Press Enter to close this status window"
