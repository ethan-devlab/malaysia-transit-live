[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSCommandPath
Set-Location $repositoryRoot

if (-not (Test-Path -LiteralPath ".env.local")) {
    throw ".env.local is required to identify the local Compose project."
}

& docker compose --env-file .env.local -f compose.local.yml down
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose could not stop Malaysia Transit Live."
}
