# Local CTP pre-submit. Stop the ship if this fails.
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

Write-Host "=== fbargarage presubmit ===" -ForegroundColor Cyan

$validator = Join-Path $PSScriptRoot "validate-doc-meta.ps1"
& $validator -RepoRoot $RepoRoot -IncludeReadme
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$changelog = Join-Path $RepoRoot "CHANGELOG.md"
if (Test-Path $changelog) {
    & $validator -RepoRoot $RepoRoot -Path "CHANGELOG.md"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

python -m compileall -q src scripts
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: python compileall" -ForegroundColor Red
    exit 1
}

Write-Host "Presubmit PASSED" -ForegroundColor Green
exit 0
