#!/usr/bin/env bash
#
# Install "Auto-Keka" into your Linux application menu (name + icon), so it
# launches like a normal app instead of showing up as "python".
#
#   bash packaging/build_linux_app.sh
#
# Creates a .desktop launcher in ~/.local/share/applications and an icon in
# ~/.local/share/icons. Find "Auto-Keka" in your app menu afterwards.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || { echo "Run ./setup.sh first ($PY missing)"; exit 1; }

ICON_DIR="$HOME/.local/share/icons"
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$ICON_DIR" "$APPS_DIR"

"$PY" "$REPO/packaging/make_icon.py" "$ICON_DIR/auto-keka.png"

cat > "$APPS_DIR/auto-keka.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Auto-Keka
Comment=Keka auto attendance — clock in/out
Exec=$PY $REPO/keka_ui.py
Icon=$ICON_DIR/auto-keka.png
Terminal=false
Categories=Utility;Office;
StartupWMClass=Auto-Keka
EOF
chmod +x "$APPS_DIR/auto-keka.desktop"
update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo "✓ Installed 'Auto-Keka' to your application menu."
echo "  Icon: $ICON_DIR/auto-keka.png"
echo "  Launcher: $APPS_DIR/auto-keka.desktop"
