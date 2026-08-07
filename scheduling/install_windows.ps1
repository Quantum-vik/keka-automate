# Install Keka auto-attendance schedule on Windows (Task Scheduler).
# Run in PowerShell (as your normal user):
#   powershell -ExecutionPolicy Bypass -File scheduling\install_windows.ps1
#
# Creates 4 tasks under the "\Keka\" folder using the ScheduledTasks cmdlets
# (Execute + Argument are passed separately, so paths with spaces are safe).
# Punch tasks are headless; the reauth tasks are Interactive so the login
# browser + dialog can appear.
$ErrorActionPreference = 'Stop'

$Keka = Split-Path -Parent $PSScriptRoot
$Py   = Join-Path $Keka ".venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "ERROR: $Py not found. Run setup.ps1 first (or create the venv):" -ForegroundColor Red
    Write-Host "  python -m venv `"$Keka\.venv`""
    Write-Host "  `"$Py`" -m pip install -r `"$Keka\requirements.txt`""
    Write-Host "  `"$Py`" -m playwright install chromium"
    exit 1
}

# Clock times from .env (KEKA_IN_TIME / KEKA_OUT_TIME, "HH:MM"), default 09:00/18:00.
# The GUI writes these to the per-user data dir (must match keka_common.py
# DATA_DIR); fall back to a legacy repo-local .env.
function Get-EnvTime($key, $default) {
    $envFile = Join-Path $env:APPDATA 'Auto-Keka\.env'
    if (-not (Test-Path $envFile)) { $envFile = Join-Path $Keka '.env' }
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern "^$key=(.+)$" | Select-Object -First 1
        if ($line) { return $line.Matches[0].Groups[1].Value.Trim() }
    }
    return $default
}
$InTime  = Get-EnvTime 'KEKA_IN_TIME'  '09:00'
$OutTime = Get-EnvTime 'KEKA_OUT_TIME' '18:00'

$Weekdays  = @("Monday","Tuesday","Wednesday","Thursday","Friday")
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# Arguments are quoted individually; Register-ScheduledTask handles the rest.
$ActIn  = New-ScheduledTaskAction -Execute $Py -Argument "`"$Keka\keka_punch_in.py`""
$ActOut = New-ScheduledTaskAction -Execute $Py -Argument "`"$Keka\keka_punch_out.py`""
$ActChk = New-ScheduledTaskAction -Execute $Py -Argument "`"$Keka\keka_check.py`""

$TrigIn  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekdays -At $InTime
$TrigOut = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekdays -At $OutTime
$TrigChk = New-ScheduledTaskTrigger -Daily  -At "10:00"
$TrigLgn = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask -Force -TaskPath "\Keka\" -TaskName "PunchIn"     -Action $ActIn  -Trigger $TrigIn  -Principal $Principal | Out-Null
Register-ScheduledTask -Force -TaskPath "\Keka\" -TaskName "PunchOut"    -Action $ActOut -Trigger $TrigOut -Principal $Principal | Out-Null
Register-ScheduledTask -Force -TaskPath "\Keka\" -TaskName "Reauth"      -Action $ActChk -Trigger $TrigChk -Principal $Principal | Out-Null
Register-ScheduledTask -Force -TaskPath "\Keka\" -TaskName "ReauthLogon" -Action $ActChk -Trigger $TrigLgn -Principal $Principal | Out-Null

Write-Host "Installed Keka tasks (9 AM in / 6 PM out, Mon-Fri; reauth daily 10 AM + logon)." -ForegroundColor Green
Write-Host "View:   Get-ScheduledTask -TaskPath '\Keka\'"
Write-Host "Remove: Get-ScheduledTask -TaskPath '\Keka\' | Unregister-ScheduledTask -Confirm:`$false"
Write-Host "Logs:   $Keka\logs\"
Write-Host ""
Write-Host "Note: tasks run only while you're logged in (no stored password, by design)."
