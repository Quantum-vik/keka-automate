#!/usr/bin/env bash
#
# Install Keka auto-attendance schedule on Linux (cron).
#   bash scheduling/install_linux.sh
#
# Punch jobs are headless. The reauth watchdog opens a browser + dialog, so it
# needs your graphical session. We snapshot your CURRENT desktop env vars
# (DISPLAY / WAYLAND_DISPLAY / XDG_RUNTIME_DIR / DBUS) and bake them into the
# cron line — run this from inside your desktop session, not over SSH.
set -euo pipefail

KEKA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$KEKA/.venv/bin/python"
LOG="$KEKA/logs/cron.log"
UID_NUM="$(id -u)"

if [ ! -x "$PY" ]; then
    echo "ERROR: $PY not found. Run ./setup.sh first (or create the venv):"
    echo "  python3 -m venv $KEKA/.venv && $KEKA/.venv/bin/pip install -r $KEKA/requirements.txt"
    echo "  $PY -m playwright install chromium"
    exit 1
fi

# Snapshot the graphical-session env so the watchdog can open a window under cron.
GUI_ENV=""
[ -n "${DISPLAY:-}" ]         && GUI_ENV="${GUI_ENV}DISPLAY=$DISPLAY "
[ -n "${WAYLAND_DISPLAY:-}" ] && GUI_ENV="${GUI_ENV}WAYLAND_DISPLAY=$WAYLAND_DISPLAY "
GUI_ENV="${GUI_ENV}XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$UID_NUM} "
GUI_ENV="${GUI_ENV}DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$UID_NUM/bus} "

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo "WARNING: no DISPLAY/WAYLAND_DISPLAY detected — the reauth watchdog can't"
    echo "         open a browser here. Run keka_setup.py manually when it expires."
fi

CRON_IN="0 9 * * 1-5 $PY $KEKA/keka_punch_in.py >> $LOG 2>&1"
CRON_OUT="0 18 * * 1-5 $PY $KEKA/keka_punch_out.py >> $LOG 2>&1"
CRON_CHK="0 10 * * * ${GUI_ENV}$PY $KEKA/keka_check.py >> $LOG 2>&1"

( crontab -l 2>/dev/null | grep -v "keka_punch\|keka_check"; \
  echo "$CRON_IN"; echo "$CRON_OUT"; echo "$CRON_CHK" ) | crontab -

echo "Installed Keka cron jobs:"
echo "  Punch in   9:00 AM Mon-Fri"
echo "  Punch out  6:00 PM Mon-Fri"
echo "  Reauth     10:00 AM daily"
echo "Verify with:  crontab -l"
echo "Logs in:      $KEKA/logs/"
