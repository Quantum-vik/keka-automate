#!/usr/bin/env bash
# Assemble Auto-Keka.app from the SPM build product.
#
# There is no .xcodeproj here on purpose: the project builds with Command Line
# Tools alone (`swift build`), so the bundle is laid out by hand the same way
# the cross-platform Auto-Keka.app wrapper already is.
#
#   ./build-app.sh [--release] [--core /path/to/compiled-core]
#
# --core copies a Nuitka-compiled Python core in as `auto-keka-core`, making the
# bundle self-contained. Without it the app falls back to $AUTOKEKA_REPO/.venv
# for development.
set -euo pipefail

cd "$(dirname "$0")"

CONFIG=debug
CORE_BIN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --release) CONFIG=release; shift ;;
    --core)    CORE_BIN="${2:?--core needs a path}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

echo "==> swift build ($CONFIG)"
swift build -c "$CONFIG"

BIN="$(swift build -c "$CONFIG" --show-bin-path)/AutoKeka"
[ -x "$BIN" ] || { echo "build produced no binary at $BIN" >&2; exit 1; }

APP="build/Auto-Keka.app"
echo "==> assembling $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/AutoKeka"

if [ -n "$CORE_BIN" ]; then
  [ -x "$CORE_BIN" ] || { echo "core is not executable: $CORE_BIN" >&2; exit 1; }
  cp "$CORE_BIN" "$APP/Contents/MacOS/auto-keka-core"
  echo "    bundled core: $CORE_BIN"
else
  echo "    no core bundled — will fall back to \$AUTOKEKA_REPO/.venv at runtime"
fi

# LSUIElement makes this a menu-bar app with no Dock icon, which is the point
# of the native client. The window is still reachable from the dropdown.
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>              <string>Auto-Keka</string>
  <key>CFBundleDisplayName</key>       <string>Auto-Keka</string>
  <key>CFBundleExecutable</key>        <string>AutoKeka</string>
  <key>CFBundleIdentifier</key>        <string>com.autokeka.mac</string>
  <key>CFBundlePackageType</key>       <string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>CFBundleVersion</key>           <string>1</string>
  <key>LSMinimumSystemVersion</key>    <string>13.0</string>
  <key>LSUIElement</key>               <true/>
  <key>NSHighResolutionCapable</key>   <true/>
</dict>
</plist>
PLIST

# Dev convenience: without a bundled core the app has no way to find the repo
# when launched from Finder (no inherited environment), so record it. Release
# builds bundle a core and never consult this.
if [ -z "$CORE_BIN" ]; then
  REPO_ROOT="$(cd .. && pwd)"
  /usr/libexec/PlistBuddy -c "Add :AutoKekaRepo string $REPO_ROOT" \
    "$APP/Contents/Info.plist" >/dev/null
  echo "    dev fallback repo: $REPO_ROOT"
fi

if [ -f ../packaging/icon.icns ]; then
  cp ../packaging/icon.icns "$APP/Contents/Resources/AppIcon.icns"
  /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" \
    "$APP/Contents/Info.plist" >/dev/null 2>&1 || true
fi

# Ad-hoc signature so macOS will run it locally. Distribution needs a real
# Developer ID certificate plus notarisation — see the release pipeline.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 \
  && echo "    ad-hoc signed" \
  || echo "    WARNING: ad-hoc signing failed; macOS may refuse to launch it"

echo "==> built $APP"
