# Create "Auto-Keka" shortcuts on Windows (Desktop + Start Menu) with a proper
# name and icon, so it launches like a normal app instead of showing "python".
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows_app.ps1
$ErrorActionPreference = 'Stop'

$Repo   = Split-Path -Parent $PSScriptRoot
$Py     = Join-Path $Repo '.venv\Scripts\python.exe'
$Pyw    = Join-Path $Repo '.venv\Scripts\pythonw.exe'   # no console window
$Ico    = Join-Path $Repo 'packaging\auto-keka.ico'
$Script = Join-Path $Repo 'keka_ui.py'

if (-not (Test-Path $Py)) {
    Write-Host "Run setup.ps1 first ($Py missing)" -ForegroundColor Red; exit 1
}
if (-not (Test-Path $Pyw)) { $Pyw = $Py }   # fall back to python.exe if pythonw absent

# icon
& $Py (Join-Path $Repo 'packaging\make_icon.py') $Ico | Out-Null

$WshShell = New-Object -ComObject WScript.Shell
function New-Lnk($path) {
    $lnk = $WshShell.CreateShortcut($path)
    $lnk.TargetPath       = $Pyw
    $lnk.Arguments        = '"' + $Script + '"'
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
