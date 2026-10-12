[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $projectRoot "Start-KalpiTech.cmd"

if (-not (Test-Path $launcher)) {
    throw "Start-KalpiTech.cmd is missing from the project root."
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "KalpiTech.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "Start KalpiTech"
$shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,14"
$shortcut.Save()

Write-Host "Shortcut created successfully: $shortcutPath" -ForegroundColor Green
Read-Host "Press Enter to close"
