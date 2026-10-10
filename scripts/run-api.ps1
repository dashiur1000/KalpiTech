param(
    [ValidateRange(1, 65535)]
    [int]$Port = 5080,
    [switch]$NoBuild
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Create .env from .env.example and set the development passwords first.'
}

# Load only the application settings; never pass the root password to the API.
$previousPassword = $env:MYSQL_PASSWORD
$previousPort = $env:MYSQL_PORT
$previousAdminEmail = $env:ADMIN_EMAIL
$previousAdminPassword = $env:ADMIN_INITIAL_PASSWORD
try {
    $env:MYSQL_PASSWORD = $null
    $env:MYSQL_PORT = '3307'
    $env:ADMIN_EMAIL = $null
    $env:ADMIN_INITIAL_PASSWORD = $null
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^MYSQL_PASSWORD=([A-Za-z0-9]+)$') {
            $env:MYSQL_PASSWORD = $Matches[1]
        }
        elseif ($line -match '^MYSQL_PORT=([0-9]+)$') {
            $env:MYSQL_PORT = $Matches[1]
        }
        elseif ($line -match '^ADMIN_EMAIL=(.+)$') {
            $env:ADMIN_EMAIL = $Matches[1]
        }
        elseif ($line -match '^ADMIN_INITIAL_PASSWORD=(.+)$') {
            $env:ADMIN_INITIAL_PASSWORD = $Matches[1]
        }
    }
    if ([string]::IsNullOrWhiteSpace($env:MYSQL_PASSWORD) -or
        $env:MYSQL_PASSWORD -eq 'replace_with_application_password') {
        throw 'Set MYSQL_PASSWORD in .env to a development password containing letters and digits.'
    }
    Push-Location $projectRoot
    try {
        $loaderPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $loaderPython)) {
            throw 'Run scripts/setup-python.ps1 before starting the API.'
        }
        # Bootstrap finishes (or preserves the existing database) before the API starts.
        & $loaderPython (Join-Path $projectRoot 'tools/data_loader/main.py')
        if ($LASTEXITCODE -ne 0) { throw 'Data bootstrap failed. The API was not started.' }
        $runArguments = @('run', '--project', 'src/KalpiTech.Api', '--no-launch-profile', '--urls', "http://127.0.0.1:$Port")
        if ($NoBuild) { $runArguments += '--no-build' }
        & dotnet @runArguments
        if ($LASTEXITCODE -ne 0) { throw 'API process failed.' }
    }
    finally { Pop-Location }
}
finally {
    $env:MYSQL_PASSWORD = $previousPassword
    $env:MYSQL_PORT = $previousPort
    $env:ADMIN_EMAIL = $previousAdminEmail
    $env:ADMIN_INITIAL_PASSWORD = $previousAdminPassword
}
