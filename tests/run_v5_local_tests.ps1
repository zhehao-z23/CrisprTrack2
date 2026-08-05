param(
    [string]$Python = "D:\MSYS2\ucrt64\bin\python.exe",
    [string]$Matlab = "D:\Program Files\MATLAB\R2025b\bin\matlab.exe"
)

$ErrorActionPreference = "Stop"
$TestRoot = $PSScriptRoot
$RepoRoot = Split-Path -Parent $TestRoot

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python executable not found: $Python"
}
if (-not (Test-Path -LiteralPath $Matlab -PathType Leaf)) {
    throw "MATLAB executable not found: $Matlab"
}

Push-Location $RepoRoot
try {
    & $Python -m unittest `
        discover -s tests -p "test_*contract.py" -v
    if ($LASTEXITCODE -ne 0) {
        throw "Python source-contract tests failed with exit code $LASTEXITCODE"
    }

    & $Matlab -batch (
        "addpath('tests'); " +
        "test_spt_track_no_trajectory; " +
        "test_spt_track_global_gap_memory; " +
        "test_spt_batch_global_gap_integration; " +
        "test_v42_v5_spt_batch_gap_control"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "MATLAB runtime tests failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Output "V5_LOCAL_TESTS_OK"
