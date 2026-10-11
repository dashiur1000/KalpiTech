$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$sqlDirectory = Join-Path $projectRoot 'src/KalpiTech.Api/Data/Sql'
foreach ($sqlFile in Get-ChildItem -LiteralPath $sqlDirectory -Filter '*.sql' | Sort-Object Name) {
    & (Join-Path $PSScriptRoot 'invoke-sql.ps1') -File $sqlFile.FullName
}
Write-Host 'Schema ready in VotesDb. Existing data was preserved.'
