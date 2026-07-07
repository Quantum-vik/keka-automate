#!/usr/bin/env bash
#
# Build a LOCKED, source-hidden Auto-Keka binary with Nuitka (compiles Python →
# C, so buyers can't just read/patch out the license check the way they could
# with a .py or a PyInstaller .pyc).
#
#   bash packaging/build_binary.sh
#
# Output: dist/  (a onefile app for THIS OS — Nuitka can't cross-compile, so run
# this on each OS you want to ship, or use the CI matrix in .github/workflows).
#
# NOTE: Playwright + Nuitka is fiddly to bundle. This script gets you a compiled
# binary of the UI; the FIRST build may need a plugin tweak for your machine.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$REPO"
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || { echo "Run ./setup.sh --phase light first ($PY missing)"; exit 1; }

echo "▶ Installing Nuitka…"
"$PY" -m pip install --quiet nuitka ordered-set 2>/dev/null || \
  { command -v uv >/dev/null && VIRTUAL_ENV="$REPO/.venv" uv pip install nuitka ordered-set; }

OS="$(uname -s)"
COMMON=(
  --standalone --onefile --assume-yes-for-downloads
  --enable-plugin=tk-inter
  --include-data-dir="$REPO/ui=ui"
  --include-module=license
  --output-dir="$REPO/dist"
)
[ "$OS" = "Darwin" ] && COMMON+=( --macos-create-app-bundle --macos-app-name="Auto-Keka" )

echo "▶ Compiling (this takes a few minutes)…"
"$PY" -m nuitka "${COMMON[@]}" keka_ui.py

echo "✓ Built into $REPO/dist/"
echo "  The license check is compiled in — the app won't run without a valid key."
echo "  Heavy deps (Chromium + tesseract) still download on first run."
