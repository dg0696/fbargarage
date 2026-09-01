# Fetch an eBay OAuth application access token (client credentials).
# Writes EBAY_CLIENT_TOKEN to Windows Credential Manager.

param(
    [ValidateSet("sandbox", "production")]
    [string]$Environment = "sandbox"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$envFile = Join-Path $repoRoot ".env"
$store = Join-Path $repoRoot "scripts\store_ebay_secrets.py"

function Get-FbSecret {
    param([string]$Name)
    return (python $store --get $Name)
}

function Read-DotEnv {
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }
        $parts = $line -split "=", 2
        if ($parts.Count -eq 2) {
            $values[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
    return $values
}

function Set-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )
    $lines = @()
    $found = $false
    if (Test-Path $Path) {
        $lines = Get-Content $Path
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^\s*$([regex]::Escape($Key))\s*=") {
                $lines[$i] = "$Key=$Value"
                $found = $true
                break
            }
        }
    }
    if (-not $found) {
        if ($lines.Count -gt 0 -and $lines[-1] -ne "") {
            $lines += ""
        }
        $lines += "$Key=$Value"
    }
    Set-Content -Path $Path -Value $lines -Encoding UTF8
}

$dotenv = Read-DotEnv -Path $envFile
$clientId = Get-FbSecret "EBAY_CLIENT_ID"
$clientSecret = Get-FbSecret "EBAY_CLIENT_SECRET"

if ([string]::IsNullOrWhiteSpace($clientId) -or [string]::IsNullOrWhiteSpace($clientSecret)) {
    Write-Error "Store EBAY_CLIENT_ID and EBAY_CLIENT_SECRET with python scripts/store_ebay_secrets.py --set NAME"
}

if ($Environment -eq "sandbox") {
    $tokenUrl = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
} else {
    $tokenUrl = "https://api.ebay.com/identity/v1/oauth2/token"
}

# Client-credentials scope URL is always api.ebay.com, even for sandbox tokens.
$scope = "https://api.ebay.com/oauth/api_scope"

$basicAuth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${clientId}:${clientSecret}"))
$body = "grant_type=client_credentials&scope=$([uri]::EscapeDataString($scope))"

Write-Host "Requesting application token from $Environment..."

$response = Invoke-RestMethod -Method Post -Uri $tokenUrl -Headers @{
    Authorization = "Basic $basicAuth"
    Accept = "application/json"
    "Accept-Language" = "en-US"
} -ContentType "application/x-www-form-urlencoded" -Body $body

$accessToken = $response.access_token
$expiresIn = $response.expires_in

if ([string]::IsNullOrWhiteSpace($accessToken)) {
    Write-Error "Token response did not include access_token."
}

$accessToken | python $store --set EBAY_CLIENT_TOKEN | Out-Null
Set-DotEnvValue -Path $envFile -Key "EBAY_API_ENV" -Value $Environment

Write-Host ""
Write-Host "Token saved to Windows Credential Manager (expires in $expiresIn seconds)."
Write-Host "Seller orders/finances need a user OAuth token (ebay_user_oauth.ps1)."
