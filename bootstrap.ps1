<#
    Auto-Keka bootstrap (Windows).

    The downloadable shortcut runs THIS first. Using only built-in PowerShell, it:
      1. Installs the "light" deps (Python venv + pip packages) if missing, behind
         a small "Setting up..." splash — one time only.
      2. Launches keka_ui.py, which opens the real window and installs the HEAVY
         deps (Chromium + tesseract) in the background, live in that window.

    No terminal steps for the user — download, double-click, follow the wizard.
#>

$ErrorActionPreference = 'Stop'
$Here    = $PSScriptRoot
$VenvPy  = Join-Path $Here '.venv\Scripts\python.exe'
$VenvPyW = Join-Path $Here '.venv\Scripts\pythonw.exe'
$Ui      = Join-Path $Here 'keka_ui.py'
$SetupPs = Join-Path $Here 'setup.ps1'

function Test-LightReady {
    if (-not (Test-Path $VenvPy)) { return $false }
    & $VenvPy -c "import webview" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Start-App {
    $exe = if (Test-Path $VenvPyW) { $VenvPyW } elseif (Test-Path $VenvPy) { $VenvPy } else { 'python' }
    Start-Process -FilePath $exe -ArgumentList "`"$Ui`"" -WorkingDirectory $Here | Out-Null
}

if (Test-LightReady) { Start-App; return }

# ── Splash while the light install runs in a hidden background process ──────────
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Auto-Keka'
$form.Size = New-Object System.Drawing.Size(440, 210)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(238, 244, 242)

$title = New-Object System.Windows.Forms.Label
$title.Text = 'Setting up Auto-Keka'
$title.Font = New-Object System.Drawing.Font('Segoe UI', 15, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(15, 58, 52)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(28, 26)
$form.Controls.Add($title)

$sub = New-Object System.Windows.Forms.Label
$sub.Text = 'Getting the app ready — this happens only once.'
$sub.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$sub.ForeColor = [System.Drawing.Color]::FromArgb(75, 107, 100)
$sub.AutoSize = $true
$sub.Location = New-Object System.Drawing.Point(30, 60)
$form.Controls.Add($sub)

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Style = 'Marquee'
$bar.MarqueeAnimationSpeed = 30
$bar.Size = New-Object System.Drawing.Size(370, 20)
$bar.Location = New-Object System.Drawing.Point(30, 95)
$form.Controls.Add($bar)

$status = New-Object System.Windows.Forms.Label
$status.Text = 'Starting...'
$status.Font = New-Object System.Drawing.Font('Segoe UI', 9)
$status.ForeColor = [System.Drawing.Color]::FromArgb(119, 147, 140)
$status.AutoSize = $false
$status.Size = New-Object System.Drawing.Size(370, 20)
$status.Location = New-Object System.Drawing.Point(30, 125)
$form.Controls.Add($status)

$logFile = Join-Path $Here 'logs\bootstrap.log'
New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null
$proc = Start-Process -FilePath 'powershell' `
    -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$SetupPs`"", '-Phase', 'light' `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $logFile

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 300
$timer.Add_Tick({
    if (Test-Path $logFile) {
        $last = Get-Content $logFile -Tail 1 -ErrorAction SilentlyContinue
        if ($last) { $status.Text = $last }
    }
    if ($proc.HasExited) { $timer.Stop(); $form.Close() }
})
$timer.Start()
[void]$form.ShowDialog()

if (Test-LightReady) {
    Start-App
} else {
    [System.Windows.Forms.MessageBox]::Show(
        "Setup could not finish. Try running setup.ps1 in PowerShell:`n`n  .\setup.ps1 -Phase light",
        'Auto-Keka', 'OK', 'Warning') | Out-Null
}
