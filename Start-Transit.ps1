[CmdletBinding()]
param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSCommandPath
Set-Location $repositoryRoot

if (-not (Test-Path -LiteralPath ".env.local")) {
    Copy-Item -LiteralPath ".env.local.example" -Destination ".env.local"
    throw "Created .env.local. Set DJANGO_SECRET_KEY, POSTGRES_PASSWORD, and VITE_MAPTILER_KEY before starting."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running. Start it, then run this script again."
}

$composeArguments = @("--env-file", ".env.local", "-f", "compose.local.yml")
$upArguments = @("up", "--detach")
if ($Rebuild) {
    $upArguments += "--build"
}
& docker compose @composeArguments @upArguments
if ($LASTEXITCODE -ne 0) {
    $initLogs = (& docker compose @composeArguments logs --no-color --tail 80 init 2>&1 | Out-String)
    if ($initLogs -match "password authentication failed") {
        throw "The existing PostgreSQL volume was initialized with a different POSTGRES_PASSWORD. To preserve local data, restore its original POSTGRES_PASSWORD in .env.local. To intentionally discard local data, follow the destructive recovery steps in README.md."
    }
    throw "Docker Compose could not start Malaysia Transit Live."
}

$requiredServices = @("api", "worker", "beat", "web", "egress-proxy")
$deadline = (Get-Date).AddMinutes(2)
do {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/v1/healthz" -UseBasicParsing -TimeoutSec 3
        $healthStates = @{}
        foreach ($service in $requiredServices) {
            $containerId = (& docker compose @composeArguments ps -q $service).Trim()
            if (-not $containerId) {
                $healthStates[$service] = "missing"
                continue
            }
            $healthStates[$service] = (& docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $containerId).Trim()
        }
        $allHealthy = @($healthStates.Values | Where-Object { $_ -ne "healthy" }).Count -eq 0
        if ($response.StatusCode -eq 200 -and $allHealthy) {
            Start-Process "http://127.0.0.1:8080"
            exit 0
        }
    } catch {
    }
    if ((Get-Date) -ge $deadline) {
        throw "The local stack did not become healthy within two minutes. Run .\\Status-Transit.ps1, then docker compose --env-file .env.local -f compose.local.yml logs <service>."
    }
    Start-Sleep -Seconds 2
} while ($true)
