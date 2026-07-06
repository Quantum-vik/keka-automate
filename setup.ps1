<#
.SYNOPSIS
    Keka Automate — one-shot Windows installer. Mirrors setup.sh for Windows.

.DESCRIPTION
    Run once after cloning the repo:

        .\setup.ps1

    Does EVERYTHING: Python venv, dependencies, Playwright Chromium,
    tesseract OCR, .env credentials, one-time OTP login, Windows Task Scheduler.

    Safe to re-run — skips steps already done.

.PARAMETER NoLogin
    Skip the interactive OTP login step (Step 7).

.PARAMETER NoSchedule
    Skip installing the Windows Task Scheduler tasks (Step 8).

.PARAMETER Help
    Print usage and exit.

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -NoLogin
    .\setup.ps1 -NoSchedule
    .\setup.ps1 -Help
#>

[CmdletBinding()]
param(
    [switch]$NoLogin,
    [switch]$NoSchedule,
    [Alias('h')]
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

# ── Help ───────────────────────────────────────────────────────────────────────
if ($Help) {
    Write-Host @"
Keka Automate setup (Windows). Usage: .\setup.ps1 [options]
  -NoLogin      Skip the interactive OTP login step
  -NoSchedule   Skip installing the Task Scheduler tasks
  -Help / -h    Show this help

Runs everything by default: venv, deps, Chromium, tesseract, .env, login, schedule.
"@
    exit 0
}

# ── Locate repo root ───────────────────────────────────────────────────────────
$Keka = $PSScriptRoot
Set-Location $Keka

# ── Pretty output helpers ──────────────────────────────────────────────────────
function Step { param($msg) Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Ok   { param($msg) Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn { param($msg) Write-Host "  !   $msg" -ForegroundColor Yellow }
function Die  { param($msg) Write-Host "  ERR $msg" -ForegroundColor Red; exit 1 }

# ── 1. Python ──────────────────────────────────────────────────────────────────
Step "1. Checking Python"
$PyBin = $null
foreach ($candidate in @('python', 'py')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        try {
            $null = & $candidate --version 2>&1
            if ($LASTEXITCODE -eq 0) { $PyBin = $candidate; break }
        } catch { }
    }
}
if (-not $PyBin) {
    Die "Python not found. Install Python 3.9+ from https://python.org and re-run."
}
$PyVer = (& $PyBin --version 2>&1)
Ok "$PyBin — $PyVer"

# ── 2. Virtual environment ─────────────────────────────────────────────────────
Step "2. Creating virtual environment (.venv)"
$VenvPy = Join-Path $Keka '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPy)) {
    & $PyBin -m venv (Join-Path $Keka '.venv')
    if (-not (Test-Path $VenvPy)) {
        Die "venv creation failed — .venv\Scripts\python.exe not found. Check your Python installation."
    }
    Ok "created .venv"
} else {
    Ok ".venv already exists"
}

# ── 3. Python dependencies ─────────────────────────────────────────────────────
Step "3. Installing Python dependencies"
& $VenvPy -m pip install --quiet --upgrade pip
& $VenvPy -m pip install --quiet -r (Join-Path $Keka 'requirements.txt')
Ok "playwright, pytesseract, pillow installed"

# ── 4. Playwright Chromium ─────────────────────────────────────────────────────
Step "4. Installing Playwright's Chromium browser"
& $VenvPy -m playwright install chromium
Ok "Chromium ready"

# ── 5. tesseract OCR engine ────────────────────────────────────────────────────
Step "5. Checking tesseract (captcha reader)"
if (Get-Command tesseract -ErrorAction SilentlyContinue) {
    $tessVer = (& tesseract --version 2>&1) | Select-Object -First 1
    Ok "already installed: $tessVer"
} else {
    Warn "tesseract not found on PATH — attempting install via winget"
    $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
    if ($wingetCmd) {
        try {
            winget install -e --id UB-Mannheim.TesseractOCR
            if ($LASTEXITCODE -eq 0) {
                Ok "tesseract installed via winget"
            } else {
                Warn "winget install returned a non-zero exit code."
                Warn "Download tesseract manually: https://github.com/UB-Mannheim/tesseract"
            }
        } catch {
            Warn "winget install failed: $_"
            Warn "Download tesseract manually: https://github.com/UB-Mannheim/tesseract"
        }
    } else {
        Warn "winget is not available on this machine."
        Warn "Download tesseract manually: https://github.com/UB-Mannheim/tesseract"
    }
    Warn "NOTE: tesseract may not be on PATH until you open a NEW PowerShell window."
    Warn "      The automation also probes 'C:\Program Files\Tesseract-OCR\tesseract.exe' automatically."
}

# ── 6. Credentials (.env) ─────────────────────────────────────────────────────
Step "6. Setting up credentials (.env)"
$EnvFile  = Join-Path $Keka '.env'
$NeedsEnv = $true
if (Test-Path $EnvFile) {
    $envContent = Get-Content $EnvFile -Raw
    if ($envContent -match 'KEKA_PASSWORD=[^\r\n]+') {
        $NeedsEnv = $false
        Ok ".env already present and has KEKA_PASSWORD — leaving as is"
    }
}
if ($NeedsEnv) {
    Write-Host "  Enter your Keka details (stored locally in .env, never uploaded):"
    $KUrl  = Read-Host "    Company Keka URL (e.g. https://acme.keka.com)"
    $KMail = Read-Host "    Email"
    $KPassSecure = Read-Host "    Password" -AsSecureString
    $KPass = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
                 [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($KPassSecure))
    @(
        "# Keka credentials + tenant. Private — keep access restricted.",
        "KEKA_BASE_URL=$KUrl",
        "KEKA_EMAIL=$KMail",
        "KEKA_PASSWORD=$KPass"
    ) | Set-Content -Path $EnvFile -Encoding UTF8
    Ok ".env created"
}

# ── 7. One-time login (you enter the OTP) ─────────────────────────────────────
Step "7. Logging in to Keka (one-time OTP)"
if ($NoLogin) {
    Ok "skipped (-NoLogin)"
} else {
    $DoLogin     = $true
    $SessionFile = Join-Path $Keka 'session.json'
    if (Test-Path $SessionFile) {
        $ans = Read-Host "  A saved session already exists. Re-do the login? [y/N]"
        if ($ans -notmatch '^[yY]') { $DoLogin = $false }
    }
    if ($DoLogin) {
        Write-Host "  A browser will open. Complete any 2FA / OTP prompt, then it saves your session."
        & $VenvPy (Join-Path $Keka 'keka_setup.py')
        if (-not (Test-Path $SessionFile)) {
            Die "Login didn't complete — no session saved. Re-run .\setup.ps1"
        }
        Ok "session saved"
    } else {
        Ok "keeping existing session"
    }
}

# ── 8. Schedule it ─────────────────────────────────────────────────────────────
Step "8. Installing the schedule (Windows Task Scheduler)"
if ($NoSchedule) {
    Ok "skipped (-NoSchedule)"
} else {
    $InstallScript = Join-Path $Keka 'scheduling\install_windows.ps1'
    if (-not (Test-Path $InstallScript)) {
        Die "Cannot find scheduling\install_windows.ps1 — is the repo complete?"
    }
    & $InstallScript
}

# ── Done ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "All set! " -ForegroundColor Green -NoNewline
Write-Host "Keka Automate will clock you in at 9 AM and out at 6 PM, Mon-Fri."
Write-Host "   Logs:        $Keka\logs\"
Write-Host "   Test it now: & `"$VenvPy`" `"$Keka\keka_punch_in.py`"   (then keka_punch_out.py)"
Write-Host ""
