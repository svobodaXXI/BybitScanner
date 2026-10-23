[CmdletBinding()]
param(
 [ValidateSet("EDITOR","TERMINAL")][string]$Mode,
 [ValidatePattern('^[A-Z0-9]{2,32}USDT$')][string]$Symbol,
 [ValidateSet("15s","1m","5m","15m","1h","1d")][string]$Timeframe,
 [ValidatePattern('^[A-Za-z0-9_.:-]{1,128}$')][string]$SignalId
)
$ErrorActionPreference = "Stop"
$port = 4173
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot "start_workspace_web.ps1"
if (!(Test-Path $launcher)) { throw "Workspace web launcher is missing; integrate PR #582" }
$signalQuery = if ($SignalId) { "&signal_id=$([uri]::EscapeDataString($SignalId))" } else { "" }
$localUrl = "http://127.0.0.1:$port/?mode=$Mode&symbol=$Symbol&timeframe=$Timeframe$signalQuery"
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
    $remoteUrl = "$($uri.GetLeftPart([System.UriPartial]::Path).TrimEnd('/'))/?mode=$Mode&symbol=$Symbol&timeframe=$Timeframe$signalQuery"
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
  $deliveryArgs = @("--mode", $Mode, "--symbol", $Symbol, "--timeframe", $Timeframe)
  if ($SignalId) { $deliveryArgs += @("--signal-id", $SignalId) }
  $deliveryOutput = @(& $python $delivery @deliveryArgs)
  $deliveryOutput | ForEach-Object { Write-Host $_ }
  if ($LASTEXITCODE -eq 0) {
    $qrLine = $deliveryOutput | Where-Object { $_ -like "QR_FILE=*" } | Select-Object -First 1
    if ($qrLine) {
      $verifiedQr = [string]$qrLine.Substring(8)
      if (Test-Path -LiteralPath $verifiedQr) {
        Write-Host "Verified mobile QR: $verifiedQr"
        Start-Process -FilePath $verifiedQr
      }
    }
  }
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "Verified Telegram QR delivery failed. The local PC browser remains open."
  }
}
Read-Host "Press Enter to close this status window"
