#Requires -Version 5.1
<#
One-time, pinned replacement of the already installed GitHub Actions forced
command handler. Does not alter SSH keys, GitHub secrets, services or PAPER DB.
Existing root owner SSH access is only used for this explicit setup action.
#>
param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$ApprovedMainSha,
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[0-9]{1,3}(\.[0-9]{1,3}){3}$')]
    [string]$VpsHost,
    [Parameter(Mandatory=$true)]
    [string]$OwnerSshKey
)
$ErrorActionPreference='Stop'
$repo='svobodaXXI/BybitScanner'
$prior='fe3290e74323fdf368fd01a788fb0fdadb4f3171'
$target='root@' + $VpsHost
$known=Join-Path $env:USERPROFILE '.ssh\known_hosts'
foreach($command in @('ssh','scp','ssh-keygen')){
    if(-not (Get-Command $command -ErrorAction SilentlyContinue)){throw "Missing $command"}
}
if(-not (Test-Path -LiteralPath $OwnerSshKey -PathType Leaf)){
    throw 'Trusted owner SSH key is unavailable'
}
if(-not (Test-Path -LiteralPath $known -PathType Leaf)){
    throw 'Trusted known_hosts is unavailable'
}
& ssh-keygen -F $VpsHost -f $known > $null
if($LASTEXITCODE -ne 0){throw 'Unrecognized VPS host key; do not auto-trust'}
if($ApprovedMainSha -eq $prior){throw 'Target equals previously installed handler'}
$oldFile=Join-Path $env:TEMP ('paper-vps-prior-' + [guid]::NewGuid().ToString('N') + '.py')
$newFile=Join-Path $env:TEMP ('paper-vps-new-' + [guid]::NewGuid().ToString('N') + '.py')
$nonce=[guid]::NewGuid().ToString('N')
$staged='/var/tmp/bybitscanner-vps-diag-' + $nonce + '.py'
$opts=@('-i',$OwnerSshKey,'-o','BatchMode=yes','-o','IdentitiesOnly=yes',
    '-o','PasswordAuthentication=no','-o','StrictHostKeyChecking=yes',
    '-o',('UserKnownHostsFile='+$known),'-o','ConnectTimeout=10',
    '-o','ForwardAgent=no')
try {
    Invoke-WebRequest ("https://raw.githubusercontent.com/$repo/$prior/ci/paper_vps_ops.py") -OutFile $oldFile -UseBasicParsing
    Invoke-WebRequest ("https://raw.githubusercontent.com/$repo/$ApprovedMainSha/ci/paper_vps_ops.py") -OutFile $newFile -UseBasicParsing
    if((Get-Item $oldFile).Length -lt 5000 -or (Get-Item $newFile).Length -lt 5000){
        throw 'Pinned source unexpectedly short'
    }
    $oldDigest=(Get-FileHash -LiteralPath $oldFile -Algorithm SHA256).Hash.ToLowerInvariant()
    $newDigest=(Get-FileHash -LiteralPath $newFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if($oldDigest -eq $newDigest){throw 'Pinned helper is unchanged'}
    & scp @opts -q $newFile ($target + ':' + $staged)
    if($LASTEXITCODE -ne 0){throw 'Pinned helper transfer failed'}
    $setup=@'
set -eu
umask 077
test "$(id -u)" -eq 0
src="__SRC__"
old="__OLD__"
new="__NEW__"
target="/usr/local/libexec/bybitscanner-paper-vps.py"
test -f "$target" && test ! -L "$target"
test "$(stat -c '%u:%a' "$target")" = "0:700"
test "$(sha256sum "$target" | cut -d ' ' -f1)" = "$old"
test -f "$src" && test ! -L "$src"
test "$(sha256sum "$src" | cut -d ' ' -f1)" = "$new"
/usr/bin/python3 -B -c 'import ast,sys; ast.parse(open(sys.argv[1],encoding="utf-8").read())' "$src"
next="/usr/local/libexec/.bybitscanner-paper-vps-__NONCE__.py"
test ! -e "$next" && test ! -L "$next"
install -o root -g root -m 0700 "$src" "$next"
test "$(sha256sum "$next" | cut -d ' ' -f1)" = "$new"
mv -T -- "$next" "$target"
rm -f -- "$src"
test "$(sha256sum "$target" | cut -d ' ' -f1)" = "$new"
echo 'DIAGNOSTICS_HANDLER_INSTALLED: restricted SSH, no runtime changes'
'@
    $setup=$setup.Replace('__SRC__',$staged).Replace('__OLD__',$oldDigest).Replace('__NEW__',$newDigest).Replace('__NONCE__',$nonce)
    $setup | & ssh -T @opts $target '/bin/sh -s'
    if($LASTEXITCODE -ne 0){throw 'Pinned handler update BLOCKED: inspect without retry'}
}
finally {
    if(Test-Path -LiteralPath $oldFile){Remove-Item -LiteralPath $oldFile -Force}
    if(Test-Path -LiteralPath $newFile){Remove-Item -LiteralPath $newFile -Force}
}
