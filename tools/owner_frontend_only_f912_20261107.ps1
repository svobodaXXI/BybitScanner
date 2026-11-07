# BybitScanner: exact-SHA frontend-only publication, no PAPER runtime mutation.
# Owner-authorized one-shot for installed f9123737. All build work is on Windows.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$sourceSha = 'f9123737fdacc658548160109c6c4e1685710899'
$publisherSha = '5cc8ab57dd0187982bafd89d35b2111b9ef88bdb'
$oldIndexSha256 = '4459dfa76e55628d3e9ef8b653c904c8bc3147548de77535127779581be552c0'
$vps = 'root@83.217.213.181'
$key = Join-Path $env:USERPROFILE '.ssh\bybitscanner_laptop'
if (-not (Test-Path -LiteralPath $key -PathType Leaf)) {
    throw 'BLOCKED: SSH identity absent; no VPS mutation'
}
if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue)) {
    throw 'BLOCKED: OpenSSH client absent; no VPS mutation'
}
if (-not (Get-Command scp.exe -ErrorAction SilentlyContinue)) {
    throw 'BLOCKED: OpenSSH scp absent; no VPS mutation'
}

$sshOptions = @(
    '-i', $key,
    '-o', 'BatchMode=yes',
    '-o', 'IdentitiesOnly=yes',
    '-o', 'PasswordAuthentication=no',
    '-o', 'StrictHostKeyChecking=yes',
    '-o', 'ConnectTimeout=10',
    '-o', 'ConnectionAttempts=1'
)
$remotePython = 'cd /opt/BybitScanner && PYTHONDONTWRITEBYTECODE=1 /opt/BybitScanner/venv/bin/python -'

# No here-doc on the remote shell: Python reads the SSH stdin to EOF.
$preflight = @'
from pathlib import Path
import hashlib
from tools.vps_release_identity import verify_release
from tools.paper_maintenance import _durable_editor_freeze, _editor_runtime_ready

sha = 'f9123737fdacc658548160109c6c4e1685710899'
expected = '4459dfa76e55628d3e9ef8b653c904c8bc3147548de77535127779581be552c0'
root = Path('/opt/BybitScanner')
actual = verify_release(root)
if actual != sha:
    raise SystemExit('BLOCKED: installed Gitless SHA changed; no mutation')
identity = _durable_editor_freeze(root, Path('/etc/bybitscanner/paper.env'))
if not _editor_runtime_ready(sha, identity):
    raise SystemExit('BLOCKED: EDITOR_ONLY Backend/Telegram/Scanner/Autopilot unproven')
index = Path('/var/www/bybitscanner/index.html')
if not index.is_file() or index.is_symlink():
    raise SystemExit('BLOCKED: HTTPS Terminal index missing or symlink')
observed = hashlib.sha256(index.read_bytes()).hexdigest()
if observed != expected:
    raise SystemExit('BLOCKED: HTTPS Terminal index drifted; no mutation; ' + observed)
print('READ_ONLY_PREFLIGHT_OK', actual, observed)
'@
Write-Host '=== READ-ONLY VPS PREFLIGHT ==='
$preflight | & ssh.exe @sshOptions $vps $remotePython
if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: VPS preflight failed; no VPS mutation' }

# Use isolated Windows TEMP; do not touch the user's checkout or installed app.
$work = Join-Path $env:TEMP ('BybitScanner-ui-f912-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
Write-Host "LOCAL_WORK=$work"

# Exact GitHub commit archive via TLS. No mutable branch checkout.
$sourceRoot = Join-Path $work 'source'
New-Item -ItemType Directory -Path $sourceRoot | Out-Null
Write-Host '=== FETCH EXACT SOURCE ==='
$commit = Invoke-RestMethod -Uri "https://api.github.com/repos/svobodaXXI/BybitScanner/commits/$sourceSha" -Headers @{ 'Accept' = 'application/vnd.github+json'; 'User-Agent' = 'BybitScanner-frontend-only' }
if ($commit.sha -cne $sourceSha) { throw 'BLOCKED: GitHub commit identity mismatch' }
$gitTool = Get-Command git.exe -ErrorAction SilentlyContinue
if ($gitTool) {
    # Sparse fetch transfers only the frontend files and verifies Git HEAD.
    & git.exe -C $sourceRoot init -q
    if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: git init failed' }
    & git.exe -C $sourceRoot remote add origin 'https://github.com/svobodaXXI/BybitScanner.git'
    if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: git origin failed' }
    & git.exe -C $sourceRoot sparse-checkout init --cone
    if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: sparse checkout init failed' }
    & git.exe -C $sourceRoot sparse-checkout set terminal/frontend
    if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: sparse checkout path failed' }
    & git.exe -C $sourceRoot fetch --depth=1 origin $sourceSha
    if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: exact Git fetch failed' }
    & git.exe -C $sourceRoot checkout --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: exact Git checkout failed' }
    $gitHead = (& git.exe -C $sourceRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $gitHead -cne $sourceSha) {
        throw 'BLOCKED: Source Git HEAD is not expected SHA'
    }
    $frontend = Join-Path $sourceRoot 'terminal\frontend'
} else {
    # Without Git, consume immutable GitHub commit archive over TLS.
    $zip = Join-Path $work 'source.zip'
    Invoke-WebRequest -Uri "https://api.github.com/repos/svobodaXXI/BybitScanner/zipball/$sourceSha" -OutFile $zip -UseBasicParsing -Headers @{ 'User-Agent' = 'BybitScanner-frontend-only' }
    $expanded = Join-Path $work 'source-archive'
    Expand-Archive -LiteralPath $zip -DestinationPath $expanded
    $sourceDirectories = @(Get-ChildItem -LiteralPath $expanded -Directory)
    if ($sourceDirectories.Count -ne 1) { throw 'BLOCKED: Unexpected archive structure' }
    $frontend = Join-Path $sourceDirectories[0].FullName 'terminal\frontend'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'package-lock.json'))) {
    throw 'BLOCKED: Missing locked frontend dependencies'
}

# Reuse compatible Node; otherwise use a temporary official portable version,
# checksum-verified using Node.js's own SHASUMS256.txt.
$usePortable = $true
$nodeTool = Get-Command node.exe -ErrorAction SilentlyContinue
$npmTool = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($nodeTool -and $npmTool) {
    try {
        $v = (& node.exe --version).Trim().TrimStart('v').Split('.')
        if (([int]$v[0] -gt 22) -or ([int]$v[0] -eq 22 -and [int]$v[1] -ge 12)) {
            $usePortable = $false
        }
    } catch { $usePortable = $true }
}
if ($usePortable) {
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
        throw 'BLOCKED: Portable Node builder supports Windows x64 only'
    }
    $version = 'v22.16.0'
    $nodeArchive = "node-$version-win-x64.zip"
    $nodeZip = Join-Path $work $nodeArchive
    $checksums = Join-Path $work 'SHASUMS256.txt'
    Write-Host '=== FETCH PINNED PORTABLE NODE ==='
    Invoke-WebRequest -Uri "https://nodejs.org/dist/$version/$nodeArchive" -OutFile $nodeZip -UseBasicParsing
    Invoke-WebRequest -Uri "https://nodejs.org/dist/$version/SHASUMS256.txt" -OutFile $checksums -UseBasicParsing
    $checksumLine = Get-Content -LiteralPath $checksums | Where-Object { $_ -match [regex]::Escape($nodeArchive) + '$' } | Select-Object -First 1
    if (-not $checksumLine) { throw 'BLOCKED: Missing pinned official Node SHA256' }
    $checksumMatch = [regex]::Match($checksumLine, '^([0-9a-f]{64})\s+node-v22\.16\.0-win-x64\.zip$')
    if (-not $checksumMatch.Success) { throw 'BLOCKED: Invalid official Node SHASUMS format' }
    $nodeDigest = (Get-FileHash -LiteralPath $nodeZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($nodeDigest -ne $checksumMatch.Groups[1].Value) { throw 'BLOCKED: Portable Node archive integrity failure' }
    $nodeExtract = Join-Path $work 'node'
    Expand-Archive -LiteralPath $nodeZip -DestinationPath $nodeExtract
    $env:Path = (Join-Path $nodeExtract 'node-v22.16.0-win-x64') + ';' + $env:Path
}

Write-Host '=== BUILD EXACT-SHA FRONTEND ==='
Push-Location $frontend
try {
    & npm.cmd ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: npm ci failed' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: exact-SHA frontend build failed' }
} finally {
    Pop-Location
}
$dist = Join-Path $frontend 'dist'
$index = Join-Path $dist 'index.html'
if (-not (Test-Path -LiteralPath $index)) { throw 'BLOCKED: Built index.html missing' }
$jsFiles = @(Get-ChildItem -LiteralPath (Join-Path $dist 'assets') -File -Filter '*.js')
if ($jsFiles.Count -eq 0) { throw 'BLOCKED: No generated JavaScript files' }
# ASCII-only markers: Windows PowerShell 5.1 opens UTF-8 .ps1 without BOM as ANSI.
# The CSS-class string literals survive Vite minification and prove the
# exact Autopilot first-screen component was included in the JS bundle.
$screenMarker = $false
foreach ($file in $jsFiles) {
    $compiledJs = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
    if ($compiledJs.Contains('autopilot-first-screen') -and
        $compiledJs.Contains('autopilot-utility-stack')) {
        $screenMarker = $true
        break
    }
}
if (-not $screenMarker) { throw 'BLOCKED: Autopilot first-screen component missing from built JS' }

# Compare FileSystemInfo paths, not string lengths: Windows TEMP can use an
# 8.3 prefix (SVOBOD~1), while Get-ChildItem expands it to SVOBODA21.
$builtIndex = (Get-Item -LiteralPath $index).FullName
$builtAssets = (Get-Item -LiteralPath (Join-Path $dist 'assets')).FullName
$files = @{}
foreach ($file in (Get-ChildItem -LiteralPath $dist -File -Recurse)) {
    if ($file.FullName -eq $builtIndex) {
        $relative = 'index.html'
    } elseif ($file.Directory.FullName -eq $builtAssets) {
        $relative = 'assets/' + $file.Name
    } else {
        throw "BLOCKED: Unexpected generated file $($file.Name)"
    }
    $files[$relative] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifest = [ordered]@{ source_sha = $sourceSha; files = $files }
$manifestPath = Join-Path $dist 'frontend-release.json'
$manifestJson = $manifest | ConvertTo-Json -Depth 8 -Compress
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, (New-Object System.Text.UTF8Encoding($false)))
$bundle = Join-Path $work 'frontend.zip'
Compress-Archive -Path (Join-Path $dist '*') -DestinationPath $bundle -CompressionLevel Optimal

# Source-pinned publisher from the already-merged, reviewed PR #927.
$publisher = Join-Path $work 'vps_terminal_frontend_publish.py'
$publisherUri = "https://raw.githubusercontent.com/svobodaXXI/BybitScanner/$publisherSha/tools/vps_terminal_frontend_publish.py"
Invoke-WebRequest -Uri $publisherUri -OutFile $publisher -UseBasicParsing
if (-not ((Get-Content -LiteralPath $publisher -Raw -Encoding UTF8).Contains('def publish_frontend('))) {
    throw 'BLOCKED: Publisher source missing expected entrypoint'
}
Write-Host "LOCAL_BUNDLE_VERIFIED files=$($files.Count) source=$sourceSha"

# One protected scratch directory for the two approved transfer files.
Write-Host '=== STAGE STATIC-ONLY PACKAGE ==='
$remoteDir = (& ssh.exe @sshOptions $vps 'umask 077; mktemp -d /var/tmp/bybitscanner-ui-f912-XXXXXXXX').Trim()
if ($LASTEXITCODE -ne 0 -or $remoteDir -notmatch '^/var/tmp/bybitscanner-ui-f912-[A-Za-z0-9]{8}$') {
    throw 'BLOCKED: Remote isolated scratch staging failed; no frontend mutation'
}
& scp.exe @sshOptions $bundle $publisher "${vps}:$remoteDir/"
if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: Static package transfer failed; no frontend mutation' }

# Re-check all original Editor invariants immediately before atomic static switch.
# Neither preflight nor this entrypoint starts/stops services or writes to SQL.
$publish = @'
from pathlib import Path, PurePosixPath
import hashlib
import importlib.util
import json
import os
import sys
import zipfile
from tools.vps_release_identity import verify_release
from tools.paper_maintenance import _durable_editor_freeze, _editor_runtime_ready

sha, scratch_name, expected_old_hash = sys.argv[1:4]
root = Path('/opt/BybitScanner')
scratch = Path(scratch_name)
if verify_release(root) != sha:
    raise SystemExit('BLOCKED: Installed release changed before publish')
identity = _durable_editor_freeze(root, Path('/etc/bybitscanner/paper.env'))
if not _editor_runtime_ready(sha, identity):
    raise SystemExit('BLOCKED: EDITOR_ONLY proof changed before publish')
webroot = Path('/var/www/bybitscanner')
observed = hashlib.sha256((webroot / 'index.html').read_bytes()).hexdigest()
if observed != expected_old_hash:
    raise SystemExit('BLOCKED: Existing UI index changed before publish')

bundle = scratch / 'frontend.zip'
publisher_file = scratch / 'vps_terminal_frontend_publish.py'
if not bundle.is_file() or bundle.is_symlink() or not publisher_file.is_file() or publisher_file.is_symlink():
    raise SystemExit('BLOCKED: Isolated upload missing or changed')
dist = scratch / 'dist'
dist.mkdir(mode=0o700)
with zipfile.ZipFile(bundle) as archive:
    total = 0
    for entry in archive.infolist():
        rel = PurePosixPath(entry.filename)
        if entry.is_dir():
            continue
        safe = (len(rel.parts) == 1 and str(rel) in ('index.html','frontend-release.json')) or (len(rel.parts) == 2 and rel.parts[0] == 'assets')
        if not safe or any(x in ('..','.') for x in rel.parts) or '\\' in entry.filename:
            raise SystemExit('BLOCKED: Unsafe bundle path')
        if entry.file_size > 100 * 1024 * 1024:
            raise SystemExit('BLOCKED: Oversized bundle member')
        total += entry.file_size
        if total > 100 * 1024 * 1024:
            raise SystemExit('BLOCKED: Oversized bundle')
        destination = dist.joinpath(*rel.parts)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.write_bytes(archive.read(entry))

spec = importlib.util.spec_from_file_location('bybitscanner_static_only_publisher', publisher_file)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.inspect_bundle(dist, sha)
result = module.publish_frontend(sha, bundle=dist, root=root,
                                  expected_index_sha256=expected_old_hash)
if not result.startswith('FRONTEND_READY:'):
    raise SystemExit('BLOCKED: Unproven static publish receipt')
with (dist / 'frontend-release.json').open(encoding='utf-8') as handle:
    sealed = json.load(handle)
for name, expected in sealed['files'].items():
    deployed = webroot.joinpath(*PurePosixPath(name).parts)
    if hashlib.sha256(deployed.read_bytes()).hexdigest() != expected:
        raise SystemExit('BLOCKED: Static frontend postcheck failed: ' + name)
print('FRONTEND_STATIC_INSTALL_VERIFIED')
print('SOURCE_SHA=' + sha)
print('INDEX_SHA256=' + sealed['files']['index.html'])
print('EDITOR_ONLY_REMAINS_READ_ONLY')
'@
Write-Host '=== PUBLISH STATIC FRONTEND ONLY ==='
$publish | & ssh.exe @sshOptions $vps "$remotePython $sourceSha $remoteDir $oldIndexSha256"
if ($LASTEXITCODE -ne 0) {
    throw 'BLOCKED: Remote publication or postcheck unproven; inspect printed reason before any retry'
}
Write-Host 'FRONTEND_INSTALLATION_VERIFIED (browser visual acceptance still required)' -ForegroundColor Green
