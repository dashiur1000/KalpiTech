$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Create .env from .env.example and set the development passwords first.'
}

# Load only the application settings; never pass the root password to the API.
$previousPassword = $env:MYSQL_PASSWORD
$previousPort = $env:MYSQL_PORT
try {
    $env:MYSQL_PASSWORD = $null
    $env:MYSQL_PORT = '3307'
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^MYSQL_PASSWORD=([A-Za-z0-9]+)$') {
            $env:MYSQL_PASSWORD = $Matches[1]
        }
        elseif ($line -match '^MYSQL_PORT=([0-9]+)$') {
            $env:MYSQL_PORT = $Matches[1]
        }
    }
    if ([string]::IsNullOrWhiteSpace($env:MYSQL_PASSWORD) -or
        $env:MYSQL_PASSWORD -eq 'replace_with_application_password') {
        throw 'Set MYSQL_PASSWORD in .env to a development password containing letters and digits.'
    }
    Push-Location $projectRoot
    try {
        dotnet run --project src/KalpiTech.Api --no-launch-profile --urls http://127.0.0.1:5080
        if ($LASTEXITCODE -ne 0) { throw 'API process failed.' }
    }
    finally { Pop-Location }
}
finally {
    $env:MYSQL_PASSWORD = $previousPassword
    $env:MYSQL_PORT = $previousPort
}
