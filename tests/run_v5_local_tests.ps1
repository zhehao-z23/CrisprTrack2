param(
    [string]$Python = "python",
    [string]$Matlab = "D:\Program Files\MATLAB\R2025b\bin\matlab.exe"
)

$ErrorActionPreference = "Stop"
$TestRoot = $PSScriptRoot
$RepoRoot = Split-Path -Parent $TestRoot

$PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
if ($null -eq $PythonCommand) {
    throw "Python executable not found on PATH or at the supplied path: $Python"
}
if (-not (Test-Path -LiteralPath $Matlab -PathType Leaf)) {
    throw "MATLAB executable not found: $Matlab"
}

Push-Location $RepoRoot
try {
    & $PythonCommand.Source -m unittest `
        discover -s tests -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) {
        throw "Python tests failed with exit code $LASTEXITCODE"
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
