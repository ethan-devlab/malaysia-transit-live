[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSCommandPath
Set-Location $repositoryRoot

if (-not (Test-Path -LiteralPath ".env.local")) {
    throw ".env.local is required to inspect the local Compose project."
}

& docker compose --env-file .env.local -f compose.local.yml ps
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose could not report Malaysia Transit Live status."
}

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/v1/healthz" -UseBasicParsing -TimeoutSec 3
    "Local API health: $($response.StatusCode)"
} catch {
    "Local API health: unavailable"
}

"For service logs: docker compose --env-file .env.local -f compose.local.yml logs <service>"
