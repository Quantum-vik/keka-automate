#!/usr/bin/env bash
#
# Optionally Developer-ID-sign and notarize a macOS .app, then re-zip it.
#
#   packaging/sign_macos.sh <path-to.app> <output.zip>
#
# Reads credentials from the environment (all set by the release workflow from
# repo secrets). If APPLE_SIGNING_IDENTITY is empty this is a NO-OP that leaves
# the existing (ad-hoc / unsigned) zip untouched — so the pipeline stays green
# for forks and for maintainers who haven't set up an Apple Developer account.
# Notarization is best-effort: a signed-but-un-notarized app still ships (it
# just shows one extra Gatekeeper prompt) rather than failing the whole release.
#
# Required secrets to ENABLE signing (set in repo → Settings → Secrets):
#   APPLE_SIGNING_IDENTITY        e.g. "Developer ID Application: You (TEAMID)"
#   APPLE_CERTIFICATE_P12         base64 of the exported .p12
#   APPLE_CERTIFICATE_PASSWORD    password for that .p12
# Additionally required to also NOTARIZE:
#   APPLE_ID                      your Apple ID email
#   APPLE_APP_SPECIFIC_PASSWORD   an app-specific password for that Apple ID
#   APPLE_TEAM_ID                 your 10-char team id
set -euo pipefail

APP="${1:?usage: sign_macos.sh <app> <zip>}"
ZIP="${2:?usage: sign_macos.sh <app> <zip>}"

if [ -z "${APPLE_SIGNING_IDENTITY:-}" ]; then
  echo "sign_macos: no APPLE_SIGNING_IDENTITY — leaving unsigned build as-is"
  exit 0
fi

echo "sign_macos: signing $APP as '$APPLE_SIGNING_IDENTITY'"
KEYCHAIN="${RUNNER_TEMP:-/tmp}/autokeka-signing.keychain-db"
KPASS="$(uuidgen)"
cleanup() { security delete-keychain "$KEYCHAIN" >/dev/null 2>&1 || true; }
trap cleanup EXIT

security create-keychain -p "$KPASS" "$KEYCHAIN"
security set-keychain-settings -lut 21600 "$KEYCHAIN"
security unlock-keychain -p "$KPASS" "$KEYCHAIN"

printf '%s' "$APPLE_CERTIFICATE_P12" | base64 --decode > "${RUNNER_TEMP:-/tmp}/cert.p12"
security import "${RUNNER_TEMP:-/tmp}/cert.p12" -k "$KEYCHAIN" \
  -P "${APPLE_CERTIFICATE_PASSWORD:-}" -T /usr/bin/codesign
rm -f "${RUNNER_TEMP:-/tmp}/cert.p12"
# make the imported key usable by codesign without an interactive prompt
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KPASS" "$KEYCHAIN" >/dev/null
# put our keychain first in the search list so codesign finds the identity
security list-keychains -d user -s "$KEYCHAIN" login.keychain-db

codesign --force --deep --options runtime --timestamp \
  --sign "$APPLE_SIGNING_IDENTITY" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
echo "sign_macos: signed OK"

# Re-zip the signed app so the uploaded artifact carries the signature.
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"

if [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ]; then
  echo "sign_macos: submitting for notarization…"
  if xcrun notarytool submit "$ZIP" \
       --apple-id "$APPLE_ID" --password "$APPLE_APP_SPECIFIC_PASSWORD" \
       --team-id "$APPLE_TEAM_ID" --wait; then
    xcrun stapler staple "$APP" || echo "sign_macos: staple failed (non-fatal)"
    rm -f "$ZIP"; ditto -c -k --keepParent "$APP" "$ZIP"
    echo "sign_macos: notarized + stapled"
  else
    echo "::warning::sign_macos: notarization failed — shipping signed but un-notarized"
  fi
else
  echo "sign_macos: notarization creds absent — shipping signed (not notarized)"
fi
