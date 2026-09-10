# Code signing & notarization (optional)

The release pipeline builds **unsigned** binaries by default, and that path
always works — forks and maintainers without certificates still get green
releases. Signing turns on automatically **only when the matching repo secrets
are present** (the same OS-gated pattern Munder Difflin uses), so nothing here
is required to ship.

When a platform is unsigned, users see a one-time "unidentified developer"
prompt (macOS Gatekeeper / Windows SmartScreen). Signing removes it.

## What signing gets you

| Platform | Unsigned today | With secrets set |
|----------|----------------|------------------|
| macOS    | ad-hoc, Gatekeeper warns | Developer ID signed + notarized + stapled |
| Windows  | unsigned, SmartScreen warns | Authenticode signed + timestamped |
| Linux    | AppImage/binary, no signing model | unchanged |

Notarization is **best-effort**: if Apple's notary service fails, the release
still ships the *signed* app (one extra prompt) instead of failing.

## macOS — Developer ID (`packaging/sign_macos.sh`)

Requires an Apple Developer account ($99/yr). Add these repo secrets
(Settings → Secrets and variables → Actions):

| Secret | What it is |
|--------|------------|
| `APPLE_SIGNING_IDENTITY` | e.g. `Developer ID Application: Your Name (TEAMID)` — **presence of this enables mac signing** |
| `APPLE_CERTIFICATE_P12` | `base64 -i DeveloperID.p12` of the exported cert+key |
| `APPLE_CERTIFICATE_PASSWORD` | password you set when exporting the `.p12` |
| `APPLE_ID` | your Apple ID email — *(these three add notarization)* |
| `APPLE_APP_SPECIFIC_PASSWORD` | app-specific password (appleid.apple.com → Sign-In & Security) |
| `APPLE_TEAM_ID` | your 10-character team id |

Set only the first three → signed but not notarized. Set all six → signed + notarized + stapled.

## Windows — Authenticode (`packaging/sign_windows.ps1`)

Requires a code-signing certificate (a paid cert from a CA, or an internal one).

| Secret | What it is |
|--------|------------|
| `WINDOWS_CERTIFICATE_PFX` | `base64` of the exported `.pfx` — **presence enables Windows signing** |
| `WINDOWS_CERTIFICATE_PASSWORD` | password for that `.pfx` |

## Verifying a download

Every release ships `SHA256SUMS.txt`. Verify before running:

```bash
# macOS / Linux
shasum -a 256 -c SHA256SUMS.txt        # (or: sha256sum -c)
```
```powershell
# Windows
(Get-FileHash Auto-Keka-windows.zip -Algorithm SHA256).Hash
```
