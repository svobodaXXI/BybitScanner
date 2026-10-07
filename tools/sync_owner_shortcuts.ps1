param(
    [string]$RepoRoot = 'C:\BybitScanner'
)

$ErrorActionPreference = 'Stop'

function Decode-Utf8Base64([string]$Text) {
    return [System.Text.Encoding]::UTF8.GetString(
        [System.Convert]::FromBase64String($Text)
    )
}

$repo = [System.IO.Path]::GetFullPath($RepoRoot)
if (-not (Test-Path -LiteralPath $repo -PathType Container)) {
    throw "Repository root not found: $repo"
}

$desktop = [Environment]::GetFolderPath('Desktop')
if (-not $desktop -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
    throw 'Desktop directory is unavailable'
}

$robotShortcut = Decode-Utf8Base64 '0JfQsNC/0YPRgdC6INGA0L7QsdC+0YLQsC5sbms='

$targets = [ordered]@{}
$targets.Add('start_scanner.lnk', 'start_scanner.bat')
$targets.Add($robotShortcut, 'start_robot_runtime.bat')
$targets.Add(
    (Decode-Utf8Base64 '0J7RgdGC0LDQvdC+0LLQuNGC0Ywg0YDQvtCx0L7RgtCwLmxuaw=='),
    'stop_robot_runtime.bat'
)

# "Zapusk robota" is Robot-only: it passes ROBOT explicitly and must never rely on an
# implicit default. SCANNER is carried by start_scanner.bat; ALL has no desktop shortcut.
$intentArguments = @{}
$intentArguments[$robotShortcut] = 'ROBOT'

$shell = New-Object -ComObject WScript.Shell

foreach ($name in $targets.Keys) {
    $expectedArguments = ''
    if ($intentArguments.ContainsKey($name)) {
        $expectedArguments = $intentArguments[$name]
    }

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
    $shortcut.Arguments = $expectedArguments
    $shortcut.WorkingDirectory = $repo
    $shortcut.Save()

    $verify = $shell.CreateShortcut($shortcutPath)
    $actualTarget = [System.IO.Path]::GetFullPath($verify.TargetPath)
    $actualWorkdir = [System.IO.Path]::GetFullPath($verify.WorkingDirectory)
    if (
        -not [string]::Equals($actualTarget, $launcher, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals($actualWorkdir, $repo, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals($verify.Arguments, $expectedArguments, [System.StringComparison]::Ordinal)
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
