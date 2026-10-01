#!/usr/bin/env bash
#
# Linux: wrap the compiled onefile binary in an AppImage — one file that runs on
# any x86_64 distro and carries its own name, icon and .desktop entry.
#
#   packaging/make_appimage.sh <binary> <icon.png> <out.AppImage>
#
# Inside, the app finds its relaunch path through $APPIMAGE (set by the AppImage
# runtime), so schedules point at the .AppImage file, not its temporary mount.
set -euo pipefail

BIN="${1:?usage: make_appimage.sh <binary> <icon.png> <out.AppImage>}"
ICON="${2:?usage: make_appimage.sh <binary> <icon.png> <out.AppImage>}"
OUT="${3:?usage: make_appimage.sh <binary> <icon.png> <out.AppImage>}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
app="$work/AppDir"
mkdir -p "$app/usr/bin"
install -m 755 "$BIN" "$app/usr/bin/Auto-Keka"
cp "$ICON" "$app/auto-keka.png"

cat > "$app/auto-keka.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Auto-Keka
Comment=Keka auto attendance — clock in/out
Exec=Auto-Keka
Icon=auto-keka
Terminal=false
Categories=Utility;Office;
StartupWMClass=Auto-Keka
DESKTOP

cat > "$app/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/Auto-Keka" "$@"
APPRUN
chmod 755 "$app/AppRun"

# ponytail: tracks appimagetool's rolling "continuous" build; pin a tagged
# release here if an upstream change ever breaks the build.
tool="$work/appimagetool"
curl -fsSL --retry 3 -o "$tool" \
  https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod 755 "$tool"
# Runners have no FUSE: run the tool from its own extracted copy.
ARCH=x86_64 "$tool" --appimage-extract-and-run "$app" "$OUT"
echo "make_appimage: built $OUT"
