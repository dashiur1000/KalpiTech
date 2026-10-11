$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
    & .\.venv\Scripts\python.exe -m pip install -r tools/data_loader/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install Python dependencies.' }
}
finally { Pop-Location }
