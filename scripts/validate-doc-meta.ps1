# Validate doc audience meta for CTP / doc-review.
# Usage:
#   pwsh -File validate-doc-meta.ps1 -RepoRoot <path> [-Strict] [-Path docs]
# Exit 0 = pass; 1 = fail.

param(
    [string]$RepoRoot = (Get-Location).Path,
    [string]$Path = "docs",
    [switch]$Strict,
    [switch]$IncludeReadme
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path $RepoRoot).Path
Set-Location $RepoRoot

$known = @(
    "executive", "manager", "program-manager", "tpm", "developer",
    "technical-writer", "user", "product", "security", "designer",
    "operations", "everyone"
)

$failures = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

function Add-Fail([string]$m) { $script:failures.Add($m) | Out-Null; Write-Host "FAIL: $m" -ForegroundColor Red }
function Add-Warn([string]$m) { $script:warnings.Add($m) | Out-Null; Write-Host "WARN: $m" -ForegroundColor Yellow }
function Add-Ok([string]$m) { Write-Host "OK:   $m" -ForegroundColor Green }

Write-Host "=== doc-meta validate ($RepoRoot) ===" -ForegroundColor Cyan

$ignore = @{}
$ignoreFile = Join-Path $RepoRoot "docs\.doc-review-ignore"
if (Test-Path $ignoreFile) {
    Get-Content $ignoreFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) { $ignore[$line.Replace("\", "/")] = $true }
    }
}

$skipNames = @("adr-template.md")
$files = @()
$docsRoot = Join-Path $RepoRoot $Path
if (Test-Path $docsRoot) {
    $files += Get-ChildItem -Path $docsRoot -Recurse -Filter "*.md" -File
}
if ($IncludeReadme -and (Test-Path (Join-Path $RepoRoot "README.md"))) {
    $files += Get-Item (Join-Path $RepoRoot "README.md")
}

if ($files.Count -eq 0) {
    Add-Warn "no markdown under $Path"
    Write-Host "Doc-meta validate PASSED (nothing to check)" -ForegroundColor Green
    exit 0
}

foreach ($f in $files) {
    $rel = $f.FullName.Substring($RepoRoot.Length).TrimStart("\", "/").Replace("\", "/")
    if ($ignore.ContainsKey($rel)) { continue }
    if ($skipNames -contains $f.Name) { continue }

    $text = Get-Content -Raw -Path $f.FullName

    $hasYaml = $text -match '(?s)\A---\s*\r?\n(.*?)\r?\n---'
    $yamlBlock = $null
    if ($hasYaml) { $yamlBlock = $Matches[1] }

    $audiences = $null
    $status = $null
    $reviewed = $null
    $summary = $null

    if ($yamlBlock -and $yamlBlock -match '(?m)^audiences:\s*\[([^\]]+)\]') {
        $audiences = ($Matches[1] -split "," | ForEach-Object { $_.Trim().Trim("'" , '"') }) -join ", "
    }
    if ($yamlBlock -and $yamlBlock -match '(?m)^status:\s*(.+)$') {
        $status = $Matches[1].Trim().Trim("'" , '"')
    }
    if ($yamlBlock -and $yamlBlock -match '(?m)^doc_reviewed:\s*(.+)$') {
        $reviewed = $Matches[1].Trim().Trim("'" , '"')
    }
    if ($yamlBlock -and $yamlBlock -match '(?m)^summary:\s*(.+)$') {
        $summary = $Matches[1].Trim().Trim("'" , '"')
    }

    # Human-readable block (preferred / napshelf)
    if (-not $audiences -and $text -match '(?m)^\*\*Audiences:\*\*\s*(.+)$') {
        $audiences = $Matches[1].Trim()
    }
    if (-not $status -and $text -match '(?m)^\*\*Status:\*\*\s*(.+)$') {
        $status = $Matches[1].Trim()
    }
    if (-not $reviewed -and $text -match '(?m)^\*\*Doc-reviewed:\*\*\s*(.+)$') {
        $reviewed = $Matches[1].Trim()
    }
    if (-not $summary -and $text -match '(?m)^\*\*Summary:\*\*\s*(.+)$') {
        $summary = $Matches[1].Trim()
    }

    $hasAudienceLine = $text -match '(?m)^\*\*Audience:\*\*' -or ($yamlBlock -and $yamlBlock -match '(?m)^audience_primary:')

    if (-not $hasAudienceLine) { Add-Fail "$rel missing Audience / audience_primary" }
    if (-not $audiences) { Add-Fail "$rel missing Audiences: slug list (or YAML audiences:)" }
    if (-not $status) { Add-Fail "$rel missing Status" }
    if (-not $reviewed) { Add-Fail "$rel missing Doc-reviewed / doc_reviewed" }
    elseif ($reviewed -notmatch '^\d{4}-\d{2}-\d{2}$') {
        Add-Fail "$rel Doc-reviewed must be YYYY-MM-DD (got '$reviewed')"
    }
    if (-not $summary) { Add-Fail "$rel missing Summary" }

    if ($audiences) {
        $slugs = $audiences -split "," | ForEach-Object { $_.Trim().Trim("`"").Trim("'").Trim("``") } | Where-Object { $_ }
        foreach ($s in $slugs) {
            $slug = $s.ToLowerInvariant()
            if ($known -notcontains $slug) {
                $msg = "$rel unknown audience slug '$slug'"
                if ($Strict) { Add-Fail $msg } else { Add-Warn $msg }
            }
        }
        if ($slugs.Count -eq 0) { Add-Fail "$rel Audiences list is empty" }
    }
}

Add-Ok "checked $($files.Count) markdown file(s)"
if ($warnings.Count -gt 0) {
    Write-Host "Warnings: $($warnings.Count)" -ForegroundColor Yellow
}

if ($failures.Count -gt 0) {
    Write-Host "Doc-meta FAILED ($($failures.Count))" -ForegroundColor Red
    exit 1
}

Write-Host "Doc-meta PASSED" -ForegroundColor Green
exit 0
