param(
    [string]$RepoRoot = 'C:\BybitScanner'
)

$ErrorActionPreference = 'Stop'

$repo = [System.IO.Path]::GetFullPath($RepoRoot)
if (-not (Test-Path -LiteralPath $repo -PathType Container)) {
    throw "Repository root not found: $repo"
}

$desktop = [Environment]::GetFolderPath('Desktop')
if (-not $desktop -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
    throw 'Desktop directory is unavailable'
}

$targets = [ordered]@{
    'start_scanner.lnk'   = 'start_scanner.bat'
    'Запуск робота.lnk'   = 'start_robot_runtime.bat'
    'Остановить робота.lnk' = 'stop_robot_runtime.bat'
}

$shell = New-Object -ComObject WScript.Shell

foreach ($name in $targets.Keys) {
    $launcher = [System.IO.Path]::GetFullPath((Join-Path $repo $targets[$name]))
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "Tracked launcher not found: $launcher"
    }

    $shortcutPath = Join-Path $desktop $name
    if (-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
        throw "Owner shortcut not found: $shortcutPath"
    }

    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcher
    $shortcut.Arguments = ''
    $shortcut.WorkingDirectory = $repo
    $shortcut.Save()

    $verify = $shell.CreateShortcut($shortcutPath)
    $actualTarget = [System.IO.Path]::GetFullPath($verify.TargetPath)
    $actualWorkdir = [System.IO.Path]::GetFullPath($verify.WorkingDirectory)
    if (
        -not [string]::Equals($actualTarget, $launcher, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals($actualWorkdir, $repo, [System.StringComparison]::OrdinalIgnoreCase) -or
        $verify.Arguments
    ) {
        throw "Shortcut verification failed: $shortcutPath"
    }

    [PSCustomObject]@{
        Shortcut = $shortcutPath
        Target = $actualTarget
        WorkingDirectory = $actualWorkdir
        Arguments = $verify.Arguments
    }
}

'OWNER SHORTCUTS = CANONICAL'
