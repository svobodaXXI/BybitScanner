#Requires -Version 5.1
<#
One-time owner-side PAPER VPS bridge bootstrap. Never starts/stops a service,
writes PAPER DB, dispatches trades, or invokes maintenance. Uses existing
owner SSH only to install a root-owned forced-command handler and dedicated
public key. Secrets are uploaded by GitHub CLI, never included in chat.
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
$ErrorActionPreference = 'Stop'
$repo = 'svobodaXXI/BybitScanner'
$environment = 'paper-vps-ops'
$sshTarget = 'root@' + $VpsHost
$knownHostsPath = Join-Path $HOME '.ssh\known_hosts'
$newPrivateKey = Join-Path $HOME '.ssh\bybitscanner-paper-actions-only'
$source = 'https://raw.githubusercontent.com/' + $repo + '/' +
    $ApprovedMainSha + '/ci/paper_vps_ops.py'

function Assert-Exit([string]$label) {
    if ($LASTEXITCODE -ne 0) { throw "$label failed (exit $LASTEXITCODE)" }
}
foreach ($command in @('gh','ssh','scp','ssh-keygen')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Missing $command; bootstrap has made no VPS changes."
    }
}
if (-not (Test-Path -LiteralPath $OwnerSshKey -PathType Leaf)) {
    throw 'Existing trusted owner SSH identity not found.'
}
if (-not (Test-Path -LiteralPath $knownHostsPath -PathType Leaf)) {
    throw 'Trusted known_hosts not found; do not accept a new host key here.'
}
& gh auth status --hostname github.com *> $null
Assert-Exit 'GitHub CLI authentication'

$trusted = @(& ssh-keygen -F $VpsHost -f $knownHostsPath 2>$null |
    Where-Object {
        $_ -match '^\S+ (ssh-ed25519|ecdsa-sha2-\S+|ssh-rsa) [A-Za-z0-9+/=]+(\s.*)?$'
    })
Assert-Exit 'Trusted host key lookup'
if ($trusted.Count -lt 1) { throw 'No previously trusted SSH host key.' }
$hostKeyText = ($trusted -join [Environment]::NewLine) + [Environment]::NewLine

& gh api -X PUT "repos/$repo/environments/$environment" --silent
Assert-Exit 'GitHub environment authorization'

$download = Join-Path $env:TEMP (
    'bybitscanner-bridge-' + [guid]::NewGuid().ToString('N') + '.py')
try {
    Invoke-WebRequest -Uri $source -OutFile $download -UseBasicParsing
    if ((Get-Item -LiteralPath $download).Length -lt 1000) {
        throw 'Pinned helper content unexpectedly short'
    }
    $digest = (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant()
    if ((Test-Path -LiteralPath $newPrivateKey) -xor
        (Test-Path -LiteralPath ($newPrivateKey + '.pub'))) {
        throw 'Incomplete existing dedicated SSH key pair; inspect before retry'
    }
    if (-not (Test-Path -LiteralPath $newPrivateKey)) {
        & ssh-keygen -q -t ed25519 -f $newPrivateKey -N '""' -C 'bybitscanner-paper-actions-only'
        Assert-Exit 'Dedicated SSH key generation'
    }
    $nonce = [guid]::NewGuid().ToString('N')
    $remoteHelper = '/var/tmp/bybitscanner-paper-' + $nonce + '.py'
    $remotePub = '/var/tmp/bybitscanner-paper-' + $nonce + '.pub'
    $opts = @(
        '-i', $OwnerSshKey, '-o','BatchMode=yes','-o','IdentitiesOnly=yes',
        '-o','PasswordAuthentication=no','-o','StrictHostKeyChecking=yes',
        '-o',('UserKnownHostsFile=' + $knownHostsPath),
        '-o','ConnectTimeout=10','-o','ForwardAgent=no'
    )
    & scp @opts -q $download ($sshTarget + ':' + $remoteHelper)
    Assert-Exit 'Transfer pinned bridge handler'
    & scp @opts -q ($newPrivateKey + '.pub') ($sshTarget + ':' + $remotePub)
    Assert-Exit 'Transfer dedicated public key'

    $setup = @'
set -eu
umask 077
test "$(id -u)" -eq 0
src="__REMOTE_HELPER__"
pub="__REMOTE_PUB__"
target="/usr/local/libexec/bybitscanner-paper-vps.py"
digest="__DIGEST__"
test -f "$src" && test ! -L "$src"
test "$(sha256sum "$src" | cut -d ' ' -f1)" = "$digest"
test -f "$pub" && test ! -L "$pub"
# /usr/local/libexec is shared system-owned infrastructure. Never chmod it.
test ! -L /usr/local/libexec
if test -e /usr/local/libexec; then
    test -d /usr/local/libexec
else
    install -d -o root -g root -m 0755 /usr/local/libexec
fi
test "$(stat -c '%u' /usr/local/libexec)" = "0"
test -z "$(find /usr/local/libexec -maxdepth 0 -perm /022 -print)"
if test -e "$target" || test -L "$target"; then
    test -f "$target" && test ! -L "$target"
    test "$(sha256sum "$target" | cut -d ' ' -f1)" = "$digest"
else
    install -o root -g root -m 0700 "$src" "$target"
fi
test "$(stat -c '%u:%a' "$target")" = "0:700"
test ! -L /root/.ssh
if test -e /root/.ssh; then
    test -d /root/.ssh
else
    install -d -o root -g root -m 0700 /root/.ssh
fi
test "$(stat -c '%u' /root/.ssh)" = "0"
test -z "$(find /root/.ssh -maxdepth 0 -perm /077 -print)"
test ! -L /root/.ssh/authorized_keys
if test -e /root/.ssh/authorized_keys; then
    test -f /root/.ssh/authorized_keys
else
    install -o root -g root -m 0600 /dev/null /root/.ssh/authorized_keys
fi
test "$(stat -c '%u' /root/.ssh/authorized_keys)" = "0"
test -z "$(find /root/.ssh/authorized_keys -maxdepth 0 -perm /022 -print)"
key="$(cat "$pub")"
case "$key" in
  'ssh-ed25519 '*) ;;
  *) echo 'BLOCKED: invalid key type'; exit 2 ;;
esac
entry='restrict,command="/usr/bin/python3 /usr/local/libexec/bybitscanner-paper-vps.py forced" '"$key"
grep -Fqx -- "$entry" /root/.ssh/authorized_keys ||
  printf '%s\n' "$entry" >> /root/.ssh/authorized_keys
rm -f -- "$src" "$pub"
echo 'FORCED_COMMAND_INSTALLED: no PAPER runtime change'
'@
    $setup = $setup.Replace('__REMOTE_HELPER__', $remoteHelper).
        Replace('__REMOTE_PUB__', $remotePub).Replace('__DIGEST__', $digest)
    $setup | & ssh -T @opts $sshTarget '/bin/sh -s'
    Assert-Exit 'Install restricted VPS SSH command'

    Get-Content -LiteralPath $newPrivateKey -Raw |
      & gh secret set PAPER_VPS_SSH_PRIVATE_KEY -R $repo -e $environment
    Assert-Exit 'Environment private key'
    $hostKeyText |
      & gh secret set PAPER_VPS_SSH_KNOWN_HOSTS -R $repo -e $environment
    Assert-Exit 'Environment pinned known_hosts'
    $sshTarget |
      & gh secret set PAPER_VPS_SSH_TARGET -R $repo -e $environment
    Assert-Exit 'Environment SSH destination'
    $names = @(& gh secret list -R $repo -e $environment --json name --jq '.[].name')
    Assert-Exit 'Environment secret metadata'
    foreach ($name in @('PAPER_VPS_SSH_PRIVATE_KEY',
                        'PAPER_VPS_SSH_KNOWN_HOSTS','PAPER_VPS_SSH_TARGET')) {
        if ($name -notin $names) { throw "Environment secret missing: $name" }
    }
    Write-Host 'BRIDGE_PROVISIONED: dedicated restricted key and three environment secrets confirmed.'
    Write-Host 'No PAPER START, STOP, UPDATE, SQL, Market or LIVE action executed.'
}
finally {
    if (Test-Path -LiteralPath $download) {
        Remove-Item -LiteralPath $download -Force
    }
}
