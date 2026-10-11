# Creates the desktop shortcut "MetaScalp + <Mechi>" that starts MetaScalp and SwordCounter.
#
# Safe by design: no administrator rights, never overwrites an existing shortcut, never touches
# other shortcuts, MetaScalp settings or the BybitScanner runtime, and puts no API key anywhere.
# The shortcut starts "<PythonW> -m tools.SwordCounter.launcher" in <RepoRoot>.
#
# Usage (from the repository that contains tools\SwordCounter):
#   powershell -NoProfile -File tools\SwordCounter\create_desktop_shortcut.ps1 [-DryRun]
param(
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$PythonW = '',
    [string]$Desktop = [Environment]::GetFolderPath('Desktop'),
    [string]$MetaScalpExe = (Join-Path $env:LOCALAPPDATA 'MetaScalp\current\MetaScalp.exe'),
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

# "Mechi" written with code points so this file stays pure ASCII.
$Mechi = [string]::new([char[]](0x041C, 0x0435, 0x0447, 0x0438))
$Name = "MetaScalp + $Mechi.lnk"

# Windows expands 8.3 short names when a shortcut is saved; use the long form from the start so
# the read-back check below compares like with like.
Add-Type -Namespace SwordCounter -Name Win32 -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode, SetLastError = true)]
public static extern int GetLongPathNameW(string shortPath, System.Text.StringBuilder longPath, int bufferSize);
'@
function ConvertTo-LongPath([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $Path }
    $buffer = New-Object System.Text.StringBuilder 1024
    $length = [SwordCounter.Win32]::GetLongPathNameW($Path, $buffer, $buffer.Capacity)
    if ($length -gt 0 -and $length -lt $buffer.Capacity) { return $buffer.ToString() }
    return $Path
}
$RepoRoot = ConvertTo-LongPath ([IO.Path]::GetFullPath($RepoRoot)).TrimEnd('\')

if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot 'tools\SwordCounter\launcher.py') -PathType Leaf)) {
    throw "tools\SwordCounter\launcher.py not found under RepoRoot: $RepoRoot"
}
if (-not $PythonW) {
    $PythonW = Join-Path $RepoRoot 'venv\Scripts\pythonw.exe'
}
if (-not (Test-Path -LiteralPath $PythonW -PathType Leaf)) {
    throw "Windowless interpreter not found: $PythonW (pass -PythonW with the project's venv pythonw.exe)"
}
$PythonW = ConvertTo-LongPath ([IO.Path]::GetFullPath($PythonW))
$MetaScalpExe = ConvertTo-LongPath ([IO.Path]::GetFullPath($MetaScalpExe))
if (-not (Test-Path -LiteralPath $Desktop -PathType Container)) {
    throw "Desktop folder not found: $Desktop"
}
$Desktop = ConvertTo-LongPath ([IO.Path]::GetFullPath($Desktop))
$Link = Join-Path $Desktop $Name
if (Test-Path -LiteralPath $Link) {
    throw "A shortcut named '$Name' already exists on the Desktop; it was left untouched."
}

$Arguments = '-m tools.SwordCounter.launcher'
$Icon = if (Test-Path -LiteralPath $MetaScalpExe -PathType Leaf) { "$MetaScalpExe,0" } else { "$PythonW,0" }

Write-Output "Shortcut : $Link"
Write-Output "Target   : $PythonW"
Write-Output "Arguments: $Arguments"
Write-Output "Start in : $RepoRoot"
Write-Output "Icon     : $Icon"
if ($DryRun) {
    Write-Output 'DRY-RUN: nothing was created.'
    return
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($Link)
$Shortcut.TargetPath = $PythonW
$Shortcut.Arguments = $Arguments
$Shortcut.WorkingDirectory = $RepoRoot
$Shortcut.IconLocation = $Icon
$Shortcut.WindowStyle = 7
$Shortcut.Description = 'Starts MetaScalp and SwordCounter as two independent applications'
$Shortcut.Save()

# Verify what was written.
$Check = $Shell.CreateShortcut($Link)
if ($Check.TargetPath -ine $PythonW -or $Check.Arguments -ne $Arguments -or $Check.WorkingDirectory -ine $RepoRoot) {
    Remove-Item -LiteralPath $Link -Force
    throw 'The created shortcut did not read back as expected and was removed.'
}
Write-Output 'Created and verified.'
