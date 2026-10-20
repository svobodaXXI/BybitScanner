# BybitScanner — owner-operated frontend launcher (Windows)
# Serves the existing production React build on localhost; no Scanner/Robot starts.
# External HTTPS must be provided by a separately secured reverse proxy or
# a previously configured Cloudflare named tunnel + Access policy.
[CmdletBinding()]
param(
    [int]$Port = 4173,
    [switch]$Build,
    [string]$NamedTunnel = "",
    [switch]$AccessPolicyVerified
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $repoRoot "terminal\frontend"
if (!(Test-Path (Join-Path $frontend "package.json"))) {
    throw "Frontend package.json missing: $frontend"
}
if (!(Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "npm.cmd unavailable. Install Node.js before launching the web UI."
}
if ($Port -lt 1024 -or $Port -gt 65535) {
    throw "Port must be 1024..65535"
}
if ($NamedTunnel -and !$AccessPolicyVerified) {
    throw "Refusing HTTPS tunnel without explicit -AccessPolicyVerified (Cloudflare Access enforced)."
}
if ($NamedTunnel -and !(Get-Command cloudflared.exe -ErrorAction SilentlyContinue)) {
    throw "Named HTTPS tunnel requested but cloudflared.exe was not found."
}
if (!(Test-Path (Join-Path $frontend "node_modules"))) {
    throw "Frontend dependencies absent; install with npm ci separately."
}
if ($Build) {
    Push-Location $frontend
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    } finally { Pop-Location }
}
if (!(Test-Path (Join-Path $frontend "dist\index.html"))) {
    throw "Production build absent. Launch with -Build first."
}
$portBusy = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($portBusy) { throw "Port $Port already has a listener; refusing a second server." }
Write-Host "Starting frontend ONLY on http://127.0.0.1:$Port/"
Write-Host "No trading runtime or PAPER backend is started."
$proc = Start-Process -FilePath "npm.cmd" -ArgumentList @("exec","--","vite","preview","--host","127.0.0.1","--port",$Port,"--strictPort") -WorkingDirectory $frontend -PassThru
if (!$NamedTunnel) {
    Write-Host "Web UI PID $($proc.Id). Remote access not enabled."
    Write-Host "For HTTPS configure a protected gateway; never publicly expose /api without authentication."
    return
}
# A named tunnel is never created or made public by this script. Operator must
# configure hostname routing and enforce Cloudflare Access in advance.
Write-Warning "Confirm that this named tunnel's public hostname is protected by Cloudflare Access before proceeding."
Write-Host "UI PID $($proc.Id), starting existing named tunnel '$NamedTunnel'."
& cloudflared.exe tunnel run $NamedTunnel
if ($LASTEXITCODE -ne 0) { throw "Named tunnel exited with error" }
