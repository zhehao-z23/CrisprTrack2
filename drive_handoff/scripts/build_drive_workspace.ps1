[CmdletBinding()]
param(
    [string]$DriveRoot = 'G:\共享云端硬盘\LivevFISH data\2-25-26-dsb_E\more\zhehao',
    [string]$RawRoot = 'G:\共享云端硬盘\LivevFISH data\2-25-26-dsb_E\more\a',
    [string]$SnapshotTag = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$V5Root = (Resolve-Path -LiteralPath (Join-Path $ScriptDir '..\..')).Path
$CodeRoot = Split-Path -Parent $V5Root

if (-not (Test-Path -LiteralPath $DriveRoot -PathType Container)) {
    throw "Drive root is unavailable: $DriveRoot"
}
if (-not (Test-Path -LiteralPath $RawRoot -PathType Container)) {
    throw "Read-only raw root is unavailable: $RawRoot"
}

$Layout = @(
    'project_history',
    'manifests',
    'sherlock_handoff',
    'sherlock_handoff\scripts',
    'published_validation',
    'dsb_v5_results',
    'dsb_v5_results\a',
    'dsb_v5_results\unmapped_review',
    'code_snapshots'
)
foreach ($Relative in $Layout) {
    $Path = Join-Path $DriveRoot $Relative
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Copy-NewFile {
    param([string]$Source, [string]$Destination)
    if (Test-Path -LiteralPath $Destination) {
        $SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
        $DestinationHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
        if ($SourceHash -eq $DestinationHash) {
            Write-Host "EXISTING_IDENTICAL=$Destination"
            return
        }
        throw "Refusing to overwrite non-identical Drive file: $Destination"
    }
    Copy-Item -LiteralPath $Source -Destination $Destination
}

Copy-NewFile -Source (Join-Path $V5Root 'drive_handoff\README.md') -Destination (Join-Path $DriveRoot 'README.md')
Copy-NewFile -Source (Join-Path $V5Root 'provenance\DEVELOPMENT_HISTORY_CN.md') -Destination (Join-Path $DriveRoot 'project_history\DEVELOPMENT_HISTORY_CN.md')
Copy-NewFile -Source (Join-Path $V5Root 'provenance\DRIVE_ARCHIVE_CONTRACT_CN.md') -Destination (Join-Path $DriveRoot 'project_history\DRIVE_ARCHIVE_CONTRACT_CN.md')
Copy-NewFile -Source (Join-Path $V5Root 'CHANGELOG.md') -Destination (Join-Path $DriveRoot 'project_history\V5_CHANGELOG.md')
Copy-NewFile -Source (Join-Path $V5Root 'drive_handoff\SHERLOCK_STATE_AND_RETURN_GUIDE_CN.md') -Destination (Join-Path $DriveRoot 'sherlock_handoff\SHERLOCK_STATE_AND_RETURN_GUIDE_CN.md')

Get-ChildItem -LiteralPath (Join-Path $V5Root 'drive_handoff\scripts') -File |
    ForEach-Object {
        Copy-NewFile $_.FullName (Join-Path $DriveRoot ('sherlock_handoff\scripts\' + $_.Name))
    }

# Generate a source pointer rather than hashing/copying ~220 GiB of ND2 data.
$Nd2Map = Join-Path $DriveRoot 'manifests\SOURCE_ND2_MAP.tsv'
$MapRows = [System.Collections.Generic.List[string]]::new()
$MapRows.Add("fov_literal`tnd2_filename`tsource_drive_relative_path`tsource_local_path`tbytes`tlast_write_utc`tmapping_status")

function TsvSafe([object]$Value) {
    return ([string]$Value).Replace("`t", ' ').Replace("`r", ' ').Replace("`n", ' ')
}

$FovDirs = Get-ChildItem -LiteralPath $RawRoot -Directory | Sort-Object Name
foreach ($Fov in $FovDirs) {
    $Nd2Files = @(Get-ChildItem -LiteralPath $Fov.FullName -Recurse -File -Filter '*.nd2')
    if ($Nd2Files.Count -eq 0) {
        $MapRows.Add("$(TsvSafe $Fov.Name)`t`t`t`t0`t`tSOURCE_ND2_MISSING_REVIEW")
        continue
    }
    foreach ($Nd2 in ($Nd2Files | Sort-Object FullName)) {
        $RelativeWithinA = $Nd2.FullName.Substring($RawRoot.Length).TrimStart('\')
        $DriveRelative = '2-25-26-dsb_E/more/a/' + ($RelativeWithinA -replace '\\', '/')
        $MapRows.Add((@(
            (TsvSafe $Fov.Name),
            (TsvSafe $Nd2.Name),
            (TsvSafe $DriveRelative),
            (TsvSafe $Nd2.FullName),
            [string]$Nd2.Length,
            $Nd2.LastWriteTimeUtc.ToString('o'),
            'SOURCE_PRESENT_NOT_COPIED'
        ) -join "`t"))
    }
}
$MapText = ($MapRows -join "`n") + "`n"
if (Test-Path -LiteralPath $Nd2Map) {
    $ExistingMapText = (Get-Content -LiteralPath $Nd2Map -Raw -Encoding UTF8) -replace "`r`n", "`n"
    if ($ExistingMapText -ne $MapText) {
        throw "Refusing to overwrite a non-identical source map: $Nd2Map"
    }
    Write-Host "EXISTING_IDENTICAL=$Nd2Map"
}
else {
    [System.IO.File]::WriteAllText($Nd2Map, $MapText, [System.Text.UTF8Encoding]::new($false))
}

$ExcludedDirectoryNames = @('.git', '__pycache__', '.pytest_cache', '.mypy_cache')
$ExcludedFileNames = @('rclone.conf', '.env', 'archive_core_file_list.txt')
$LargeExampleExtensions = @('.tif', '.tiff', '.nd2', '.mat', '.npy', '.npz')

function Should-CopyFile {
    param([System.IO.FileInfo]$File, [string]$SourceRoot, [string]$Mode)
    if (-not (Test-Path -LiteralPath $File.FullName -PathType Leaf)) {
        return $false
    }
    if (($File.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        return $false
    }
    $Relative = $File.FullName.Substring($SourceRoot.Length).TrimStart('\')
    $Parts = $Relative -split '[\\/]'
    foreach ($Part in $Parts) {
        if ($ExcludedDirectoryNames -contains $Part) { return $false }
    }
    if ($ExcludedFileNames -contains $File.Name) { return $false }
    if ($File.Name -match '(?i)(credential|secret)' -or $File.Name -match '(?i)^token.*\.json$') {
        return $false
    }
    if ($Mode -eq 'code_only' -and $Relative -match '(?i)trajectory_extraction[\\/]example_data[\\/]') {
        return $false
    }
    if ($Mode -eq 'phase2_current' -and $Relative -match '(?i)^archive[\\/]packages[\\/]') {
        return $false
    }
    return $true
}

function Get-GitEvidence {
    param([string]$SourceRoot)
    $Evidence = [ordered]@{ head = 'NO_GIT'; branch = 'NO_GIT'; dirty_rows = 'NA' }
    if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot '.git'))) { return $Evidence }
    $Git = Get-Command git -ErrorAction SilentlyContinue
    if ($null -eq $Git) { return $Evidence }
    Push-Location $SourceRoot
    try {
        $Evidence.head = ((& $Git.Source rev-parse HEAD 2>$null) -join '').Trim()
        $Evidence.branch = ((& $Git.Source branch --show-current 2>$null) -join '').Trim()
        if (-not $Evidence.branch) { $Evidence.branch = 'DETACHED' }
        $Evidence.dirty_rows = @(& $Git.Source status --short 2>$null).Count
    }
    finally { Pop-Location }
    return $Evidence
}

function Export-Snapshot {
    param(
        [string]$Label,
        [string]$SourceRoot,
        [ValidateSet('code_only', 'handoff_docs', 'phase2_current')]
        [string]$Mode
    )
    if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
        throw "Snapshot source is missing: $SourceRoot"
    }
    $Destination = Join-Path $DriveRoot "code_snapshots\${Label}_${SnapshotTag}"
    if (Test-Path -LiteralPath $Destination) {
        throw "Refusing to reuse snapshot destination: $Destination"
    }
    New-Item -ItemType Directory -Path $Destination | Out-Null

    $Files = @(Get-ChildItem -LiteralPath $SourceRoot -Recurse -File -Force |
        Where-Object { Should-CopyFile $_ $SourceRoot $Mode } |
        Sort-Object FullName)

    foreach ($File in $Files) {
        $Relative = $File.FullName.Substring($SourceRoot.Length).TrimStart('\')
        $Target = Join-Path $Destination $Relative
        $TargetParent = Split-Path -Parent $Target
        if (-not (Test-Path -LiteralPath $TargetParent)) {
            New-Item -ItemType Directory -Path $TargetParent | Out-Null
        }
        Copy-Item -LiteralPath $File.FullName -Destination $Target
        (Get-Item -LiteralPath $Target).LastWriteTimeUtc = $File.LastWriteTimeUtc
    }

    $Evidence = Get-GitEvidence $SourceRoot
    $VersionPath = Join-Path $SourceRoot 'VERSION'
    $Version = if (Test-Path -LiteralPath $VersionPath) {
        (Get-Content -LiteralPath $VersionPath -Raw -Encoding UTF8).Trim()
    } else { 'NO_VERSION_FILE' }

    $Copied = @(Get-ChildItem -LiteralPath $Destination -Recurse -File)
    $Bytes = ($Copied | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $Bytes) { $Bytes = 0 }

    $Metadata = @(
        "SNAPSHOT_LABEL=$Label",
        "CREATED_UTC=$((Get-Date).ToUniversalTime().ToString('o'))",
        "SOURCE_ABSOLUTE_PATH=$SourceRoot",
        "MODE=$Mode",
        "GIT_HEAD=$($Evidence.head)",
        "GIT_BRANCH=$($Evidence.branch)",
        "SOURCE_DIRTY_ROWS=$($Evidence.dirty_rows)",
        "VERSION=$Version",
        "COPIED_FILES=$($Copied.Count)",
        "COPIED_BYTES=$Bytes",
        "EXCLUDED_DIRS=$($ExcludedDirectoryNames -join ',')",
        "EXCLUDED_FILES=$($ExcludedFileNames -join ',')",
        'CODE_ONLY_EXCLUDES=trajectory_extraction/example_data',
        'RAW_DATA_INCLUDED=NO_BY_FILTER_CONTRACT'
    )
    [System.IO.File]::WriteAllLines(
        (Join-Path $Destination '_SNAPSHOT_METADATA.txt'),
        $Metadata,
        [System.Text.UTF8Encoding]::new($false)
    )

    $HashPath = Join-Path $Destination '_FILE_SHA256.tsv'
    $HashRows = [System.Collections.Generic.List[string]]::new()
    $HashRows.Add("relative_path`tbytes`tsha256")
    Get-ChildItem -LiteralPath $Destination -Recurse -File |
        Where-Object { $_.FullName -ne $HashPath } |
        Sort-Object FullName |
        ForEach-Object {
            $Relative = $_.FullName.Substring($Destination.Length).TrimStart('\') -replace '\\', '/'
            $Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $HashRows.Add("$(TsvSafe $Relative)`t$($_.Length)`t$Hash")
        }
    [System.IO.File]::WriteAllLines($HashPath, $HashRows, [System.Text.UTF8Encoding]::new($false))

    return [pscustomobject]@{
        label = $Label
        destination = $Destination
        source = $SourceRoot
        mode = $Mode
        git_head = $Evidence.head
        version = $Version
        files = (Get-ChildItem -LiteralPath $Destination -Recurse -File).Count
        bytes = (Get-ChildItem -LiteralPath $Destination -Recurse -File |
            Measure-Object -Property Length -Sum).Sum
    }
}

$SnapshotSpecs = @(
    @{ Label = 'ref_3e65bff_code'; Source = (Join-Path $CodeRoot 'OligoLiveFish-ML-reference'); Mode = 'code_only' },
    @{ Label = 'v416_fix_5d1aa1b'; Source = (Join-Path $CodeRoot 'OligoLiveFish-ML-ZZH-v4.1.6-fix'); Mode = 'code_only' },
    @{ Label = 'v416_demo_6b3e57f'; Source = (Join-Path $CodeRoot 'OligoLiveFish-ML-ZZH-v4.1.6-demo'); Mode = 'code_only' },
    @{ Label = 'v422_833515e'; Source = (Join-Path $CodeRoot 'OligoLiveFish-ML-ZZH-v4.2-candidate-qc'); Mode = 'code_only' },
    @{ Label = 'v5_dev1_docs'; Source = $V5Root; Mode = 'code_only' },
    @{ Label = 'sherlock_handoff_20260727'; Source = (Join-Path $CodeRoot '2026-07-27_sherlock_handoff'); Mode = 'handoff_docs' },
    @{ Label = 'phase2_current_20260728'; Source = (Join-Path $CodeRoot '2026-07-28_OligoLiveFISH_phase2_analysis'); Mode = 'phase2_current' }
)

$Results = foreach ($Spec in $SnapshotSpecs) {
    Export-Snapshot -Label $Spec.Label -SourceRoot $Spec.Source -Mode $Spec.Mode
}

$IndexTsv = Join-Path $DriveRoot "manifests\CODE_SNAPSHOT_INDEX_${SnapshotTag}.tsv"
$IndexRows = [System.Collections.Generic.List[string]]::new()
$IndexRows.Add("label`tdestination`tsource`tmode`tgit_head`tversion`tfiles`tbytes")
foreach ($Result in $Results) {
    $IndexRows.Add((@(
        (TsvSafe $Result.label),
        (TsvSafe $Result.destination),
        (TsvSafe $Result.source),
        (TsvSafe $Result.mode),
        (TsvSafe $Result.git_head),
        (TsvSafe $Result.version),
        [string]$Result.files,
        [string]$Result.bytes
    ) -join "`t"))
}
[System.IO.File]::WriteAllLines($IndexTsv, $IndexRows, [System.Text.UTF8Encoding]::new($false))

$IndexMd = Join-Path $DriveRoot 'code_snapshots\INDEX_CN.md'
if (Test-Path -LiteralPath $IndexMd) {
    throw "Refusing to overwrite existing snapshot index: $IndexMd"
}
$Md = [System.Collections.Generic.List[string]]::new()
$Md.Add('# 代码快照索引')
$Md.Add('')
$Md.Add("生成时间（UTC）：$((Get-Date).ToUniversalTime().ToString('o'))")
$Md.Add('')
$Md.Add('每个新快照都含 `_SNAPSHOT_METADATA.txt` 和 `_FILE_SHA256.tsv`。已有的')
$Md.Add('`OligoLiveFish-ML-ZZH-v5-dev1_20260803T165041Z` 是早期 Sherlock 上传快照，')
$Md.Add('本次没有覆盖它。')
$Md.Add('')
$Md.Add('| 快照 | Git HEAD | VERSION | 文件数 | 字节数 |')
$Md.Add('| --- | --- | --- | ---: | ---: |')
foreach ($Result in $Results) {
    $Folder = Split-Path -Leaf $Result.destination
    $Md.Add(('| `{0}` | `{1}` | `{2}` | {3} | {4} |' -f $Folder, $Result.git_head, $Result.version, $Result.files, $Result.bytes))
}
$Md.Add('')
$Md.Add('完整路径与源路径见 `../manifests/CODE_SNAPSHOT_INDEX_*.tsv`。')
[System.IO.File]::WriteAllLines($IndexMd, $Md, [System.Text.UTF8Encoding]::new($false))

Write-Host '========== DRIVE WORKSPACE =========='
Write-Host "DRIVE_ROOT=$DriveRoot"
Write-Host "SOURCE_ND2_MAP=$Nd2Map"
Write-Host "SOURCE_ND2_ROWS=$($MapRows.Count - 1)"
Write-Host "SNAPSHOT_INDEX=$IndexTsv"
$Results | Format-Table label, git_head, version, files, bytes -AutoSize
Write-Host 'DRIVE_WORKSPACE_BUILD_OK'
