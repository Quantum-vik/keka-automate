#!/usr/bin/env bash
#
# Build "Auto-Keka.app" — a proper macOS app bundle (name + icon) that launches
# the desktop UI, so it shows as "Auto-Keka" in the Dock instead of "python3.13".
#
#   bash packaging/build_macos_app.sh
#
# Output: <repo>/Auto-Keka.app  (double-click it, or drag to /Applications).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
APP="$REPO/Auto-Keka.app"
TMPICON="/tmp/autokeka_icon.png"
ICONSET="/tmp/AutoKeka.iconset"

# Icon generation needs Pillow (a light dep). Bootstrap it if the venv is absent.
[ -x "$PY" ] || { echo "▶ venv missing — installing light deps…"; bash "$REPO/setup.sh" --phase light; }
[ -x "$PY" ] || { echo "Could not create the venv. Run ./setup.sh manually."; exit 1; }

echo "▶ Generating icon…"
"$PY" "$REPO/packaging/make_icon.py" "$TMPICON"

echo "▶ Building icon.icns…"
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for sz in 16 32 128 256 512; do
    sips -z $sz $sz "$TMPICON" --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null
    d=$((sz*2)); sips -z $d $d "$TMPICON" --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o /tmp/AutoKeka.icns

echo "▶ Assembling Auto-Keka.app…"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp /tmp/AutoKeka.icns "$APP/Contents/Resources/icon.icns"

# The launcher runs bootstrap.py: it self-installs the deps on first run (showing
# a splash), then opens the window. It resolves the repo RELATIVE to the bundle
# so the app works on any machine while Auto-Keka.app sits in the project folder;
# if moved out (e.g. dragged to /Applications) it falls back to the build path.
cat > "$APP/Contents/MacOS/Auto-Keka" <<LAUNCH
#!/bin/bash
HERE="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
REPO="\$(cd "\$HERE/../../.." && pwd)"
[ -f "\$REPO/bootstrap.py" ] || REPO="$REPO"
cd "\$REPO" || exit 1
PY="\$(command -v python3 || echo /usr/bin/python3)"
exec "\$PY" bootstrap.py
LAUNCH
chmod +x "$APP/Contents/MacOS/Auto-Keka"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Auto-Keka</string>
  <key>CFBundleDisplayName</key><string>Auto-Keka</string>
  <key>CFBundleExecutable</key><string>Auto-Keka</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundleIdentifier</key><string>com.keka.autokeka</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
</dict>
</plist>
PLIST

touch "$APP"   # nudge Finder to pick up the new icon
echo "✓ Built $APP"
echo "  Double-click it in Finder, or drag it to /Applications."
