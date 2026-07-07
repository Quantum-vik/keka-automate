# Create "Auto-Keka" shortcuts on Windows (Desktop + Start Menu) with a proper
# name and icon, so it launches like a normal app instead of showing "python".
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows_app.ps1
$ErrorActionPreference = 'Stop'

$Repo   = Split-Path -Parent $PSScriptRoot
$Py     = Join-Path $Repo '.venv\Scripts\python.exe'
$Ico    = Join-Path $Repo 'packaging\auto-keka.ico'
$Boot   = Join-Path $Repo 'bootstrap.ps1'

# Icon generation needs Pillow (a light dep). Bootstrap it if the venv is absent.
if (-not (Test-Path $Py)) {
    Write-Host "venv missing - installing light deps..." -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo 'setup.ps1') -Phase light
}
if (-not (Test-Path $Py)) {
    Write-Host "Could not create the venv. Run setup.ps1 manually." -ForegroundColor Red; exit 1
}

# icon
& $Py (Join-Path $Repo 'packaging\make_icon.py') $Ico | Out-Null

# The shortcut launches bootstrap.ps1 (self-installs deps on first run, then opens
# the window) via a hidden PowerShell so no console window flashes.
$PwSh = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$WshShell = New-Object -ComObject WScript.Shell
function New-Lnk($path) {
    $lnk = $WshShell.CreateShortcut($path)
    $lnk.TargetPath       = $PwSh
    $lnk.Arguments        = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $Boot + '"'
    $lnk.WorkingDirectory = $Repo
    $lnk.IconLocation     = $Ico
    $lnk.Description       = 'Keka auto attendance — clock in/out'
    $lnk.Save()
}

$desktop   = [Environment]::GetFolderPath('Desktop')
$startMenu = [Environment]::GetFolderPath('Programs')
New-Lnk (Join-Path $desktop   'Auto-Keka.lnk')
New-Lnk (Join-Path $startMenu 'Auto-Keka.lnk')

Write-Host "Created 'Auto-Keka' shortcuts on the Desktop and Start Menu." -ForegroundColor Green
Write-Host "Icon: $Ico"
