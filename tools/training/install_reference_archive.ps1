[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$ArchivePath,

    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

<#
Exit codes:
  0 = installed and verified
  1 = invalid arguments/archive
  2 = manifest/schema failure
  3 = unsafe path/archive entry
  4 = destination conflict or unauthorized cleanup
  5 = installation/verification/rollback failure
#>

class ReferenceArchiveException : System.Exception {
    [int]$InstallerExitCode

    ReferenceArchiveException([string]$message, [int]$exitCode) : base($message) {
        $this.InstallerExitCode = $exitCode
    }
}

function Stop-Install {
    param([string]$Message, [int]$Code)
    throw [ReferenceArchiveException]::new($Message, $Code)
}

function Test-HasProperty {
    param($Object, [string]$Name)
    return $null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name
}

function ConvertTo-SafeRelativePath {
    param([string]$Value, [int]$FailureCode = 3)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        Stop-Install "Empty relative path is not allowed." $FailureCode
    }
    $normalized = $Value.Replace("\", "/")
    if ($normalized.StartsWith("/") -or $normalized.StartsWith("//") -or
        [System.IO.Path]::IsPathRooted($Value) -or $normalized -match '^[A-Za-z]:') {
        Stop-Install "Rooted or drive-qualified path is not allowed: $Value" $FailureCode
    }
    $parts = $normalized.Split('/')
    $invalidParts = @($parts | Where-Object {
        $_ -eq ".." -or $_ -eq "." -or [string]::IsNullOrWhiteSpace($_) -or
        $_ -match '[:*?<>|"\x00-\x1f]' -or $_.EndsWith(".") -or $_.EndsWith(" ")
    })
    if ($parts.Count -eq 0 -or $invalidParts.Count -ne 0) {
        Stop-Install "Unsafe or non-canonical relative path: $Value" $FailureCode
    }
    return ($parts -join "/")
}

function Resolve-Beneath {
    param([string]$Root, [string]$RelativePath, [int]$FailureCode = 3)

    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $candidate = [System.IO.Path]::GetFullPath(
        (Join-Path $rootFull ($RelativePath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)))
    )
    $prefix = $rootFull + [System.IO.Path]::DirectorySeparatorChar
    if (-not $candidate.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        Stop-Install "Resolved path escapes its allowed root: $RelativePath" $FailureCode
    }
    return $candidate
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-ZipLinkLikeEntry {
    param($Entry)
    $unixMode = (($Entry.ExternalAttributes -shr 16) -band 0xF000)
    $dosAttributes = ($Entry.ExternalAttributes -band 0xFFFF)
    return $unixMode -eq 0xA000 -or ($dosAttributes -band 0x400) -ne 0
}

$temporaryRoot = $null
$archive = $null
$mutationsStarted = $false
$createdFiles = [System.Collections.Generic.List[string]]::new()
$backups = [System.Collections.Generic.List[object]]::new()
$createdDirectories = [System.Collections.Generic.List[string]]::new()

try {
    try {
        $archiveFull = (Resolve-Path -LiteralPath $ArchivePath -ErrorAction Stop).Path
        $projectFull = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
    }
    catch {
        Stop-Install "Invalid archive or project path: $($_.Exception.Message)" 1
    }
    if (-not [System.IO.File]::Exists($archiveFull)) {
        Stop-Install "Archive path is not a file: $archiveFull" 1
    }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    try {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($archiveFull)
    }
    catch {
        Stop-Install "Archive cannot be opened: $($_.Exception.Message)" 1
    }

    $entryNames = @{}
    foreach ($entry in $archive.Entries) {
        $entryPath = $entry.FullName.Replace("\", "/")
        $isDirectory = $entryPath.EndsWith("/")
        $pathToValidate = if ($isDirectory) { $entryPath.TrimEnd('/') } else { $entryPath }
        $safeEntryPath = ConvertTo-SafeRelativePath $pathToValidate 3
        if ($isDirectory) {
            if ($safeEntryPath -ne "payload" -and
                -not $safeEntryPath.StartsWith("payload/", [System.StringComparison]::Ordinal)) {
                Stop-Install "Archive directory is outside payload/: $entryPath" 2
            }
        }
        elseif ($safeEntryPath -ne "reference-archive.json" -and
            -not $safeEntryPath.StartsWith("payload/", [System.StringComparison]::Ordinal)) {
            Stop-Install "Archive file is outside the manifest/payload layout: $entryPath" 2
        }
        if (Test-ZipLinkLikeEntry $entry) {
            Stop-Install "Link-like ZIP entry is not allowed: $entryPath" 3
        }
        $key = $safeEntryPath.ToLowerInvariant()
        if ($entryNames.ContainsKey($key)) {
            Stop-Install "Duplicate ZIP entry is not allowed: $safeEntryPath" 3
        }
        $entryNames[$key] = $entry
    }
    if (-not $entryNames.ContainsKey("reference-archive.json")) {
        Stop-Install "reference-archive.json is missing." 2
    }

    $temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
        "BybitScannerReferenceInstall-" + [guid]::NewGuid().ToString("N")
    )
    [void][System.IO.Directory]::CreateDirectory($temporaryRoot)
    foreach ($entryKey in $entryNames.Keys) {
        $entry = $entryNames[$entryKey]
        $entryPath = $entry.FullName.Replace("\", "/")
        if ($entryPath.EndsWith("/")) { continue }
        $target = Resolve-Beneath $temporaryRoot $entryPath 3
        [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target))
        $inputStream = $entry.Open()
        try {
            $outputStream = [System.IO.File]::Create($target)
            try { $inputStream.CopyTo($outputStream) }
            finally { $outputStream.Dispose() }
        }
        finally { $inputStream.Dispose() }
    }

    $manifestPath = Join-Path $temporaryRoot "reference-archive.json"
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        Stop-Install "Manifest JSON is malformed: $($_.Exception.Message)" 2
    }

    $required = @(
        "schema_version", "archive_type", "canonical_symbol", "case_id",
        "reference_type", "canonical_destination", "files"
    )
    foreach ($field in $required) {
        if (-not (Test-HasProperty $manifest $field)) {
            Stop-Install "Manifest field is required: $field" 2
        }
    }
    if ($manifest.schema_version -ne "1.0" -or
        $manifest.archive_type -ne "BYBITSCANNER_TRAINING_REFERENCE") {
        Stop-Install "Unsupported manifest schema or archive type." 2
    }
    $symbol = [string]$manifest.canonical_symbol
    $caseId = [string]$manifest.case_id
    $referenceType = [string]$manifest.reference_type
    if ($symbol -notmatch '^[A-Z0-9]{3,32}$') {
        Stop-Install "canonical_symbol is invalid or non-canonical." 2
    }
    if ($caseId -notmatch '^[a-z0-9][a-z0-9_-]{2,79}$') {
        Stop-Install "case_id must be a stable lowercase human-readable identifier." 2
    }
    if ($referenceType -notmatch '^[a-z0-9][a-z0-9_-]{1,63}$') {
        Stop-Install "reference_type is invalid." 2
    }
    $canonicalDestination = ConvertTo-SafeRelativePath ([string]$manifest.canonical_destination) 2
    $expectedDestination = "training/reference_patterns/$symbol/$caseId"
    if ($canonicalDestination -cne $expectedDestination) {
        Stop-Install "canonical_destination must equal $expectedDestination" 2
    }

    $referenceRoot = Join-Path $projectFull "training\reference_patterns"
    $caseRoot = Resolve-Beneath $projectFull $canonicalDestination 3
    [void](Resolve-Beneath $referenceRoot "$symbol/$caseId" 3)
    $caseExistedBefore = [System.IO.Directory]::Exists($caseRoot)

    $declaredSources = @{}
    $declaredDestinations = @{}
    $operations = [System.Collections.Generic.List[object]]::new()
    $files = @($manifest.files)
    if ($files.Count -eq 0) {
        Stop-Install "Manifest files must contain at least one declared file." 2
    }
    foreach ($file in $files) {
        foreach ($field in @("source", "destination", "role", "sha256", "install_policy")) {
            if (-not (Test-HasProperty $file $field)) {
                Stop-Install "Manifest file field is required: $field" 2
            }
        }
        $source = ConvertTo-SafeRelativePath ([string]$file.source) 3
        if (-not $source.StartsWith("payload/", [System.StringComparison]::Ordinal)) {
            Stop-Install "Declared source must be beneath payload/: $source" 2
        }
        $destination = ConvertTo-SafeRelativePath ([string]$file.destination) 3
        $sourceKey = $source.ToLowerInvariant()
        $destinationKey = $destination.ToLowerInvariant()
        if ($declaredSources.ContainsKey($sourceKey) -or
            $declaredDestinations.ContainsKey($destinationKey)) {
            Stop-Install "Duplicate declared source or destination." 2
        }
        $declaredSources[$sourceKey] = $true
        $declaredDestinations[$destinationKey] = $true
        if (-not $entryNames.ContainsKey($sourceKey)) {
            Stop-Install "Declared payload file is missing: $source" 2
        }
        $sourcePath = Resolve-Beneath $temporaryRoot $source 3
        $expectedHash = ([string]$file.sha256).ToLowerInvariant()
        if ($expectedHash -notmatch '^[0-9a-f]{64}$' -or (Get-Sha256 $sourcePath) -ne $expectedHash) {
            Stop-Install "Declared payload hash is invalid or mismatched: $source" 2
        }
        if ([string]$file.role -eq "original_source_image") {
            if (-not (Test-HasProperty $file "preserve_exact_bytes") -or
                $file.preserve_exact_bytes -ne $true -or
                -not (Test-HasProperty $file "original_filename") -or
                [string]::IsNullOrWhiteSpace([string]$file.original_filename)) {
                Stop-Install "original_source_image requires original_filename and preserve_exact_bytes=true." 2
            }
        }
        $policy = [string]$file.install_policy
        if ($policy -notin @("create_or_identical", "authorized_replace")) {
            Stop-Install "Unsupported install_policy: $policy" 2
        }
        $destinationPath = Resolve-Beneath $caseRoot $destination 3
        $destinationParent = [System.IO.Path]::GetDirectoryName($destinationPath)
        $parentCursor = $destinationParent
        while ($parentCursor.StartsWith($caseRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            if ([System.IO.File]::Exists($parentCursor)) {
                Stop-Install "A destination parent is an existing file: $destination" 4
            }
            if ($parentCursor -eq $caseRoot) { break }
            $parentCursor = [System.IO.Path]::GetDirectoryName($parentCursor)
        }
        $currentHash = $null
        $operation = if ([System.IO.File]::Exists($destinationPath)) {
            $currentHash = Get-Sha256 $destinationPath
            if ($currentHash -eq $expectedHash) {
                "IDENTICAL_NOOP"
            }
            elseif ($policy -eq "authorized_replace") {
                if (-not (Test-HasProperty $file "replacement_authorization")) {
                    Stop-Install "Replacement authorization is missing: $destination" 4
                }
                $authorization = $file.replacement_authorization
                $authorizedCurrentHash = if (Test-HasProperty $authorization "expected_current_sha256") {
                    ([string]$authorization.expected_current_sha256).ToLowerInvariant()
                } else { "" }
                if ($authorization.authorized -ne $true -or
                    $authorizedCurrentHash -notmatch '^[0-9a-f]{64}$' -or
                    $authorizedCurrentHash -ne $currentHash -or
                    -not (Test-HasProperty $authorization "reason") -or
                    [string]::IsNullOrWhiteSpace([string]$authorization.reason)) {
                    Stop-Install "Replacement is unauthorized or current hash mismatched: $destination" 4
                }
                "AUTHORIZED_REPLACE"
            }
            else {
                Stop-Install "Existing different file cannot be overwritten: $destination" 4
            }
        }
        elseif ($caseExistedBefore) { "ADD_TO_EXISTING_CASE" }
        else { "CREATE" }

        $operations.Add([pscustomobject]@{
            Source = $sourcePath
            Destination = $destinationPath
            ExpectedHash = $expectedHash
            PreflightCurrentHash = $currentHash
            Operation = $operation
            Role = [string]$file.role
        })
    }

    foreach ($entryKey in $entryNames.Keys) {
        if ($entryKey -eq "reference-archive.json") { continue }
        $entry = $entryNames[$entryKey]
        if ($entry.FullName.Replace("\", "/").EndsWith("/")) { continue }
        if (-not $entryKey.StartsWith("payload/") -or -not $declaredSources.ContainsKey($entryKey)) {
            Stop-Install "Undeclared archive payload/file is not allowed: $($entry.FullName)" 2
        }
    }

    $cleanupOperations = [System.Collections.Generic.List[object]]::new()
    if (Test-HasProperty $manifest "superseded_artifacts") {
        foreach ($cleanup in @($manifest.superseded_artifacts)) {
            foreach ($field in @("path", "expected_sha256", "created_by", "cleanup_authorized", "reason")) {
                if (-not (Test-HasProperty $cleanup $field)) {
                    Stop-Install "Superseded artifact field is required: $field" 4
                }
            }
            $cleanupRelative = ConvertTo-SafeRelativePath ([string]$cleanup.path) 3
            if (-not $cleanupRelative.StartsWith("training/reference_patterns/", [System.StringComparison]::Ordinal) -or
                $cleanup.created_by -ne "assistant_workflow" -or
                $cleanup.cleanup_authorized -ne $true -or
                [string]::IsNullOrWhiteSpace([string]$cleanup.reason)) {
                Stop-Install "Superseded artifact cleanup is not explicitly authorized: $cleanupRelative" 4
            }
            $cleanupPath = Resolve-Beneath $referenceRoot (
                $cleanupRelative.Substring("training/reference_patterns/".Length)
            ) 3
            if ($operations.Destination -contains $cleanupPath) {
                Stop-Install "Cleanup path overlaps an installation destination: $cleanupRelative" 4
            }
            if ([System.IO.File]::Exists($cleanupPath)) {
                $expectedCleanupHash = ([string]$cleanup.expected_sha256).ToLowerInvariant()
                if ($expectedCleanupHash -notmatch '^[0-9a-f]{64}$' -or
                    (Get-Sha256 $cleanupPath) -ne $expectedCleanupHash) {
                    Stop-Install "Superseded artifact hash mismatch: $cleanupRelative" 4
                }
                $cleanupOperations.Add([pscustomobject]@{
                    Path = $cleanupPath
                    PreflightCurrentHash = $expectedCleanupHash
                })
            }
            elseif (([string]$cleanup.expected_sha256).ToLowerInvariant() -notmatch '^[0-9a-f]{64}$') {
                Stop-Install "Superseded artifact expected hash is invalid: $cleanupRelative" 4
            }
        }
    }

    $emptyDirectories = [System.Collections.Generic.List[string]]::new()
    if (Test-HasProperty $manifest "cleanup_empty_directories") {
        foreach ($directory in @($manifest.cleanup_empty_directories)) {
            $relative = ConvertTo-SafeRelativePath ([string]$directory) 3
            if (-not $relative.StartsWith("training/reference_patterns/", [System.StringComparison]::Ordinal)) {
                Stop-Install "Cleanup directory is outside reference_patterns: $relative" 4
            }
            $resolved = Resolve-Beneath $referenceRoot (
                $relative.Substring("training/reference_patterns/".Length)
            ) 3
            $directoryPrefix = $resolved.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
            $authorizedChildren = @($cleanupOperations | Where-Object {
                $_.Path.StartsWith($directoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)
            })
            if ($authorizedChildren.Count -eq 0) {
                Stop-Install "Cleanup directory has no authorized superseded artifact: $relative" 4
            }
            if ([System.IO.Directory]::Exists($resolved)) {
                $remaining = @(Get-ChildItem -LiteralPath $resolved -Force | Where-Object {
                    $childPath = $_.FullName
                    -not ($cleanupOperations.Path -contains $childPath)
                })
                if ($remaining.Count -ne 0) {
                    Stop-Install "Authorized cleanup directory will not be empty: $relative" 4
                }
                $emptyDirectories.Add($resolved)
            }
        }
    }

    # Revalidate mutable targets at the preflight/mutation boundary.
    foreach ($operation in $operations) {
        $existsNow = [System.IO.File]::Exists($operation.Destination)
        if ($null -eq $operation.PreflightCurrentHash) {
            if ($existsNow) {
                Stop-Install "Destination changed after preflight: $($operation.Destination)" 4
            }
        }
        elseif (-not $existsNow -or
            (Get-Sha256 $operation.Destination) -ne $operation.PreflightCurrentHash) {
            Stop-Install "Destination changed after preflight: $($operation.Destination)" 4
        }
    }
    foreach ($cleanup in $cleanupOperations) {
        if (-not [System.IO.File]::Exists($cleanup.Path) -or
            (Get-Sha256 $cleanup.Path) -ne $cleanup.PreflightCurrentHash) {
            Stop-Install "Superseded artifact changed after preflight: $($cleanup.Path)" 4
        }
    }

    # All validation and conflict/cleanup preflight is complete before this point.
    $mutationsStarted = $true
    $backupRoot = Join-Path $temporaryRoot "transaction-backup"
    [void][System.IO.Directory]::CreateDirectory($backupRoot)

    foreach ($operation in $operations) {
        Write-Output "$($operation.Operation): $($operation.Destination)"
        if ($operation.Operation -eq "IDENTICAL_NOOP") { continue }
        $parent = [System.IO.Path]::GetDirectoryName($operation.Destination)
        if (-not [System.IO.Directory]::Exists($parent)) {
            $missing = [System.Collections.Generic.List[string]]::new()
            $cursor = $parent
            while ($cursor.StartsWith($referenceRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
                -not [System.IO.Directory]::Exists($cursor)) {
                $missing.Add($cursor)
                if ($cursor -eq $referenceRoot) { break }
                $cursor = [System.IO.Path]::GetDirectoryName($cursor)
            }
            [void][System.IO.Directory]::CreateDirectory($parent)
            foreach ($directory in $missing) { $createdDirectories.Add($directory) }
        }
        if ($operation.Operation -eq "AUTHORIZED_REPLACE") {
            $backup = Join-Path $backupRoot ([guid]::NewGuid().ToString("N"))
            [System.IO.File]::Move($operation.Destination, $backup)
            $backups.Add([pscustomobject]@{ Original = $operation.Destination; Backup = $backup })
        }
        [System.IO.File]::Copy($operation.Source, $operation.Destination, $false)
        $createdFiles.Add($operation.Destination)
    }

    foreach ($cleanup in $cleanupOperations) {
        $backup = Join-Path $backupRoot ([guid]::NewGuid().ToString("N"))
        [System.IO.File]::Move($cleanup.Path, $backup)
        $backups.Add([pscustomobject]@{ Original = $cleanup.Path; Backup = $backup })
        Write-Output "CLEANUP: $($cleanup.Path)"
    }
    foreach ($directory in ($emptyDirectories | Sort-Object Length -Descending)) {
        if ([System.IO.Directory]::Exists($directory) -and
            @(Get-ChildItem -LiteralPath $directory -Force).Count -eq 0) {
            [System.IO.Directory]::Delete($directory)
        }
    }

    foreach ($operation in $operations) {
        if (-not [System.IO.File]::Exists($operation.Destination) -or
            (Get-Sha256 $operation.Destination) -ne $operation.ExpectedHash) {
            Stop-Install "Final installation verification failed: $($operation.Destination)" 5
        }
        if ($operation.Role -eq "original_source_image") {
            $sourceBytes = [System.IO.File]::ReadAllBytes($operation.Source)
            $destinationBytes = [System.IO.File]::ReadAllBytes($operation.Destination)
            if ([Convert]::ToBase64String($sourceBytes) -cne
                [Convert]::ToBase64String($destinationBytes)) {
                Stop-Install "Original image bytes changed during installation." 5
            }
        }
    }

    if ($null -ne $archive) { $archive.Dispose(); $archive = $null }
    try {
        [System.IO.Directory]::Delete($temporaryRoot, $true)
        $temporaryRoot = $null
    }
    catch {
        Stop-Install "Temporary extraction cleanup failed: $($_.Exception.Message)" 5
    }
    Write-Output "INSTALLED_AND_VERIFIED: $canonicalDestination"
    exit 0
}
catch {
    $failure = $_.Exception
    $exitCode = if ($failure -is [ReferenceArchiveException]) {
        $failure.InstallerExitCode
    } else { 5 }
    $rollbackErrors = [System.Collections.Generic.List[string]]::new()
    if ($mutationsStarted) {
        foreach ($path in ($createdFiles | Select-Object -Unique)) {
            try { if ([System.IO.File]::Exists($path)) { [System.IO.File]::Delete($path) } }
            catch { $rollbackErrors.Add($_.Exception.Message) }
        }
        foreach ($record in ($backups | Select-Object -Reverse)) {
            try {
                $parent = [System.IO.Path]::GetDirectoryName($record.Original)
                [void][System.IO.Directory]::CreateDirectory($parent)
                if ([System.IO.File]::Exists($record.Original)) {
                    [System.IO.File]::Delete($record.Original)
                }
                if ([System.IO.File]::Exists($record.Backup)) {
                    [System.IO.File]::Move($record.Backup, $record.Original)
                }
            }
            catch { $rollbackErrors.Add($_.Exception.Message) }
        }
        foreach ($directory in ($createdDirectories | Sort-Object Length -Descending -Unique)) {
            try {
                if ([System.IO.Directory]::Exists($directory) -and
                    @(Get-ChildItem -LiteralPath $directory -Force).Count -eq 0) {
                    [System.IO.Directory]::Delete($directory)
                }
            }
            catch { $rollbackErrors.Add($_.Exception.Message) }
        }
    }
    if ($rollbackErrors.Count -gt 0) {
        Write-Error "ROLLBACK_FAILURE: $($rollbackErrors -join '; ')"
        exit 5
    }
    if ($null -ne $archive) { $archive.Dispose(); $archive = $null }
    if ($null -ne $temporaryRoot -and [System.IO.Directory]::Exists($temporaryRoot)) {
        try {
            [System.IO.Directory]::Delete($temporaryRoot, $true)
            $temporaryRoot = $null
        }
        catch {
            Write-Error "TEMPORARY_CLEANUP_FAILURE: $($_.Exception.Message)"
            exit 5
        }
    }
    Write-Error "INSTALL_FAILED[$exitCode]: $($failure.Message)"
    exit $exitCode
}
finally {
    if ($null -ne $archive) { $archive.Dispose() }
    if ($null -ne $temporaryRoot -and [System.IO.Directory]::Exists($temporaryRoot)) {
        try { [System.IO.Directory]::Delete($temporaryRoot, $true) }
        catch { Write-Warning "Temporary extraction cleanup failed: $($_.Exception.Message)" }
    }
}
