# Optionally Authenticode-sign a Windows .exe.
#
#   packaging\sign_windows.ps1 -Exe Auto-Keka.exe
#
# Reads the signing cert from env vars set by the release workflow from repo
# secrets. If WINDOWS_CERTIFICATE_PFX is empty this is a NO-OP that leaves the
# unsigned .exe untouched — so the pipeline stays green without a code-signing
# certificate (which costs money and can't be provided by forks).
#
# Secrets to ENABLE signing:
#   WINDOWS_CERTIFICATE_PFX        base64 of the exported .pfx
#   WINDOWS_CERTIFICATE_PASSWORD   password for that .pfx
param([Parameter(Mandatory=$true)][string]$Exe)

$ErrorActionPreference = 'Stop'

if (-not $env:WINDOWS_CERTIFICATE_PFX) {
    Write-Host "sign_windows: no WINDOWS_CERTIFICATE_PFX — leaving unsigned exe as-is"
    exit 0
}

$pfx = Join-Path $env:RUNNER_TEMP 'autokeka-cert.pfx'
[IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE_PFX))

# Locate signtool (ships with the Windows SDK on the GitHub runner).
$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match 'x64' } | Select-Object -First 1 -ExpandProperty FullName
if (-not $signtool) { throw "signtool.exe not found on runner" }

Write-Host "sign_windows: signing $Exe"
& $signtool sign `
    /f $pfx /p $env:WINDOWS_CERTIFICATE_PASSWORD `
    /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
    $Exe
if ($LASTEXITCODE -ne 0) { throw "signtool failed with $LASTEXITCODE" }
& $signtool verify /pa $Exe
Remove-Item $pfx -Force
Write-Host "sign_windows: signed OK"
