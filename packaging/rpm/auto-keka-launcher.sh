#!/usr/bin/env bash
#
# Auto-Keka launcher (installed as /usr/bin/auto-keka by the RPM).
#
# The RPM is self-contained: /opt/keka-automate ships its own Python venv (all
# pip deps) and Playwright's Chromium, and the system packages (tesseract,
# WebKitGTK, tkinter, …) come in as RPM dependencies. So there is nothing to set
# up at runtime — just point Playwright at the bundled browser and launch.
#
# Writable state (.env, session, logs) lives in ~/.local/share/Auto-Keka, so the
# read-only /opt tree is never modified.
set -euo pipefail

APP="/opt/keka-automate"
export PLAYWRIGHT_BROWSERS_PATH="$APP/ms-playwright"

exec "$APP/.venv/bin/python" "$APP/keka_ui.py" "$@"
