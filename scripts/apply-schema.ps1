$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot 'invoke-sql.ps1') -File (Join-Path $projectRoot 'src/KalpiTech.Api/Data/Sql/001_initial_schema.sql')
Write-Host 'Schema ready in VotesDb. Existing data was preserved.'
