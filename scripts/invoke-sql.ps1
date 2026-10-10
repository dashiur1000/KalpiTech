[CmdletBinding(DefaultParameterSetName = 'Query')]
param(
    [Parameter(Mandatory, ParameterSetName = 'File')]
    [string]$File,
    [Parameter(Mandatory, ParameterSetName = 'Query')]
    [string]$Query,
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]*$')]
    [string]$Database = 'VotesDb',
    [switch]$UseRoot
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$sql = if ($PSCmdlet.ParameterSetName -eq 'File') {
    Get-Content -LiteralPath $File -Raw -Encoding UTF8
} else { $Query }

# Credentials remain inside the container; SQL is passed through standard input.
$mysqlCommand = 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql --protocol=TCP -h 127.0.0.1 -u kalpitech --default-character-set=utf8mb4 --batch "$1"'
if ($UseRoot) {
    $mysqlCommand = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -u root --default-character-set=utf8mb4 --batch "$1"'
}
$previousEncoding = $OutputEncoding
Push-Location $projectRoot
try {
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    # Capture errors so callers can assert a particular MySQL error number.
    $ErrorActionPreference = 'Continue'
    $output = $sql | & docker compose exec -T mysql sh -c $mysqlCommand sh $Database 2>&1
    $sqlExitCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($sqlExitCode -ne 0) { throw "MySQL command failed: $($output -join [Environment]::NewLine)" }
    $output
}
finally {
    $OutputEncoding = $previousEncoding
    Pop-Location
}
