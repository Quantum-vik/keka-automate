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

# Clock times from .env (KEKA_IN_TIME / KEKA_OUT_TIME, "HH:MM"), default 09:00/18:00.
# The GUI writes these to the per-user data dir (must match keka_common.py
# DATA_DIR); fall back to a legacy repo-local .env.
ENV_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/Auto-Keka/.env"
[ -f "$ENV_FILE" ] || ENV_FILE="$KEKA/.env"
IN_TIME=$(grep -E '^KEKA_IN_TIME=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' \r"')
OUT_TIME=$(grep -E '^KEKA_OUT_TIME=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' \r"')
IN_H=$(printf '%s' "${IN_TIME:-09:00}"  | cut -d: -f1 | sed 's/^0//'); IN_H=${IN_H:-0}
IN_M=$(printf '%s' "${IN_TIME:-09:00}"  | cut -d: -f2 | sed 's/^0*//'); IN_M=${IN_M:-0}
OUT_H=$(printf '%s' "${OUT_TIME:-18:00}" | cut -d: -f1 | sed 's/^0//'); OUT_H=${OUT_H:-0}
OUT_M=$(printf '%s' "${OUT_TIME:-18:00}" | cut -d: -f2 | sed 's/^0*//'); OUT_M=${OUT_M:-0}

CRON_IN="$IN_M $IN_H * * 1-5 $PY $KEKA/keka_punch_in.py >> $LOG 2>&1"
CRON_OUT="$OUT_M $OUT_H * * 1-5 $PY $KEKA/keka_punch_out.py >> $LOG 2>&1"
# Every 6h, not once daily: a single daily slot is too easy to sleep through,
# and the check is silent unless the cookie is actually near expiry.
CRON_CHK="0 */6 * * * ${GUI_ENV}$PY $KEKA/keka_check.py >> $LOG 2>&1"

( crontab -l 2>/dev/null | grep -v "keka_punch\|keka_check"; \
  echo "$CRON_IN"; echo "$CRON_OUT"; echo "$CRON_CHK" ) | crontab -

echo "Installed Keka cron jobs:"
echo "  Punch in   ${IN_H}:$(printf '%02d' "$IN_M") Mon-Fri"
echo "  Punch out  ${OUT_H}:$(printf '%02d' "$OUT_M") Mon-Fri"
echo "  Reauth     every 6 hours"
echo "Verify with:  crontab -l"
echo "Logs in:      $KEKA/logs/"
