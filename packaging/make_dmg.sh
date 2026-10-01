#!/usr/bin/env bash
#
# macOS: wrap a .app in a compressed .dmg with the usual "drag to Applications"
# layout (the app next to an /Applications shortcut).
#
#   packaging/make_dmg.sh <path/to/App.app> <out.dmg> <volume name>
set -euo pipefail

APP="${1:?usage: make_dmg.sh <app> <out.dmg> <volume name>}"
OUT="${2:?usage: make_dmg.sh <app> <out.dmg> <volume name>}"
VOL="${3:?usage: make_dmg.sh <app> <out.dmg> <volume name>}"
[ -d "$APP" ] || { echo "make_dmg: not an app bundle: $APP"; exit 1; }

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
ditto "$APP" "$stage/$(basename "$APP")"
ln -s /Applications "$stage/Applications"

# hdiutil intermittently fails with "Resource busy" on CI runners; retry.
for attempt in 1 2 3; do
  rm -f "$OUT"
  hdiutil create -volname "$VOL" -srcfolder "$stage" -ov -format UDZO "$OUT" && break
  [ "$attempt" = 3 ] && { echo "make_dmg: hdiutil failed 3 times"; exit 1; }
  sleep 5
done
echo "make_dmg: built $OUT"
