# Install Keka auto-attendance schedule on Windows (Task Scheduler).
# Run in PowerShell (as your normal user):
#   powershell -ExecutionPolicy Bypass -File scheduling\install_windows.ps1
#
# Creates 4 tasks under the "Keka" folder. Punch tasks are headless; the reauth
# tasks are interactive (/IT) so the login browser + dialog can appear.

$Keka = Split-Path -Parent $PSScriptRoot
$Py   = Join-Path $Keka ".venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "ERROR: $Py not found. Create the venv first:" -ForegroundColor Red
    Write-Host "  python -m venv `"$Keka\.venv`""
    Write-Host "  `"$Py`" -m pip install -r `"$Keka\requirements.txt`""
    Write-Host "  `"$Py`" -m playwright install chromium"
    exit 1
}

$In  = "`"$Py`" `"$Keka\keka_punch_in.py`""
$Out = "`"$Py`" `"$Keka\keka_punch_out.py`""
$Chk = "`"$Py`" `"$Keka\keka_check.py`""

# Punch in — weekdays 09:00
schtasks /Create /F /TN "Keka\PunchIn"  /TR $In  /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:00
# Punch out — weekdays 18:00
schtasks /Create /F /TN "Keka\PunchOut" /TR $Out /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:00
# Reauth watchdog — daily 10:00 (interactive) + at logon
schtasks /Create /F /TN "Keka\Reauth"      /TR $Chk /SC DAILY /ST 10:00 /IT
schtasks /Create /F /TN "Keka\ReauthLogon" /TR $Chk /SC ONLOGON /IT

Write-Host "Installed Keka tasks. View with:  schtasks /Query /FO LIST /TN Keka\PunchIn" -ForegroundColor Green
Write-Host "Remove with: schtasks /Delete /F /TN Keka\PunchIn (and PunchOut, Reauth, ReauthLogon)"
Write-Host "Logs in: $Keka\logs\"
