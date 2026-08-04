param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
Set-Location $ProjectRoot

$env:DOCKER_CONFIG = Join-Path $ProjectRoot ".docker-codex"
New-Item -ItemType Directory -Force -Path $env:DOCKER_CONFIG | Out-Null

docker version | Out-Host
docker compose -f ".\docker-compose.local-postgres.yml" up -d

$env:GL02_PGHOST = "127.0.0.1"
$env:GL02_PGPORT = "15432"
$env:GL02_PGDATABASE = "bf_trend"
$env:GL02_PGUSER = "gl02_sync"
$env:GL02_PGPASSWORD = "gl02_local_sync"

Write-Host "Waiting for local PostgreSQL health ..."
for ($i = 1; $i -le 60; $i++) {
    $state = docker inspect --format "{{.State.Health.Status}}" bf-v3-local-postgres 2>$null
    if ($LASTEXITCODE -eq 0 -and $state -eq "healthy") {
        Write-Host "Local PostgreSQL is healthy on 127.0.0.1:15432."
        .\.venv\Scripts\python.exe .\db_sync_storage\src\init_pg.py --config .\db_sync_storage\config\sync_config.json
        exit 0
    }
    Start-Sleep -Seconds 2
}

throw "Local PostgreSQL container did not become healthy."
