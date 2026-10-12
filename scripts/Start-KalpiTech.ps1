[CmdletBinding()]
param(
    [int]$DockerWaitSeconds = 120,
    [int]$ApplicationWaitSeconds = 180
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFiles = @("-f", "compose.yaml", "-f", "compose.app.yaml")

function Stop-WithMessage {
    param([string]$Message)

    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

function Test-DockerEngine {
    & docker info *> $null
    return $LASTEXITCODE -eq 0
}

Set-Location $projectRoot

if (-not (Test-Path (Join-Path $projectRoot ".env"))) {
    Stop-WithMessage "The .env file is missing. Create it from .env.example and configure the passwords."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-WithMessage "Docker is not installed or is not available in PATH. Install and start Docker Desktop."
}

Write-Host "Starting KalpiTech..." -ForegroundColor Cyan

if (-not (Test-DockerEngine)) {
    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerDesktop)) {
        Stop-WithMessage "Docker Desktop is not running and was not found in its standard location. Start it manually and try again."
    }

    Write-Host "Starting Docker Desktop and waiting for it to become ready..."
    Start-Process $dockerDesktop
    $deadline = (Get-Date).AddSeconds($DockerWaitSeconds)
    do {
        Start-Sleep -Seconds 3
        if (Test-DockerEngine) {
            break
        }
    } while ((Get-Date) -lt $deadline)

    if (-not (Test-DockerEngine)) {
        Stop-WithMessage "Docker Desktop did not become ready in time. Check Docker Desktop and try again."
    }
}

$privateKalpiFile = Join-Path $projectRoot ".local\import\kalpi.csv"
if (-not (Test-Path $privateKalpiFile)) {
    Write-Warning "The private .local\import\kalpi.csv file is missing. Station passwords will not be loaded into a new database."
}

Write-Host "Starting the containers and waiting for the API and database..."
& docker compose @composeFiles up -d --build --wait
if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "Container startup failed. Run docker compose logs api to inspect the error."
}

$appPort = 5080
$portLine = Get-Content (Join-Path $projectRoot ".env") |
    Where-Object { $_ -match '^\s*APP_PORT\s*=\s*([0-9]+)\s*$' } |
    Select-Object -Last 1
if ($portLine) {
    $portMatch = [regex]::Match($portLine, '^\s*APP_PORT\s*=\s*([0-9]+)\s*$')
    $configuredPort = [int]$portMatch.Groups[1].Value
    if ($configuredPort -ge 1 -and $configuredPort -le 65535) {
        $appPort = $configuredPort
    }
}

$appUrl = "http://127.0.0.1:$appPort"
$healthUrl = "$appUrl/health/db"
$deadline = (Get-Date).AddSeconds($ApplicationWaitSeconds)
$ready = $false

do {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
} while ((Get-Date) -lt $deadline)

if (-not $ready) {
    Stop-WithMessage "The containers started, but KalpiTech did not pass its health check in time."
}

Write-Host "KalpiTech is ready. Opening the browser..." -ForegroundColor Green
Start-Process $appUrl
