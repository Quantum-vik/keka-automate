#!/usr/bin/env bash
#
# Install Keka auto-attendance schedule on Linux.
#   bash scheduling/install_linux.sh
#
# Uses systemd user timers where available: a punch that falls due while the
# laptop is asleep runs as soon as it wakes, and one missed while it was off or
# logged out runs at the next login. Punches carry --scheduled, so a late run
# only happens inside that day's window (no clock-in after clock-out time, no
# clocking out yesterday's session this morning). Without systemd it falls back
# to cron, which only fires on time. KEKA_SCHEDULER=cron forces cron.
#
# The reauth watchdog may open a window: under systemd it inherits the desktop
# session's DISPLAY; under cron we snapshot the CURRENT desktop env vars into
# the cron line — run this from inside your desktop session, not over SSH.
set -euo pipefail

KEKA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$KEKA/.venv/bin/python"
LOG="$KEKA/logs/cron.log"

if [ ! -x "$PY" ]; then
    echo "ERROR: $PY not found. Run ./setup.sh first (or create the venv):"
    echo "  python3 -m venv $KEKA/.venv && $KEKA/.venv/bin/pip install -r $KEKA/requirements.txt"
    echo "  $PY -m playwright install chromium"
    exit 1
fi

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo "WARNING: no DISPLAY/WAYLAND_DISPLAY detected — the reauth watchdog can't"
    echo "         open a browser here. Run keka_setup.py manually when it expires."
fi

# Clock times from .env (KEKA_IN_TIME / KEKA_OUT_TIME, "HH:MM"), default 09:00/18:00.
# The GUI writes these to the per-user data dir (must match keka_common.py
# DATA_DIR); fall back to a legacy repo-local .env. `|| true`: under pipefail a
# missing file or key made grep's exit 1 kill the script before the defaults
# applied (setup.sh writes a .env with no times).
ENV_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/Auto-Keka/.env"
[ -f "$ENV_FILE" ] || ENV_FILE="$KEKA/.env"
IN_TIME=$(grep -E '^KEKA_IN_TIME=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' \r"' || true)
OUT_TIME=$(grep -E '^KEKA_OUT_TIME=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' \r"' || true)
IN_TIME="${IN_TIME:-09:00}"
OUT_TIME="${OUT_TIME:-18:00}"

# The scheduler itself is keka_common.install_schedule_linux, shared with the
# compiled app so both install the same timers.
"$PY" - "$KEKA" "$PY" "$LOG" "$IN_TIME" "$OUT_TIME" <<'PYEOF'
import os, sys
keka, py, log, in_time, out_time = sys.argv[1:6]
sys.path.insert(0, keka)
import keka_common as kc

r = kc.install_schedule_linux(
    [py, os.path.join(keka, "keka_punch_in.py"), "--scheduled"],
    [py, os.path.join(keka, "keka_punch_out.py"), "--scheduled"],
    [py, os.path.join(keka, "keka_check.py")],
    in_time=in_time, out_time=out_time, log_file=log)
if not r["ok"]:
    print(f"ERROR: could not install the schedule ({r['method']}).")
    sys.exit(1)
if r["method"] == "systemd":
    print("Installed Keka systemd user timers (missed punches catch up on wake):")
else:
    print("Installed Keka cron jobs (on time only — no systemd user manager here):")
print(f"  Punch in   {in_time} Mon-Fri")
print(f"  Punch out  {out_time} Mon-Fri")
print("  Reauth     every 6 hours")
if r["method"] == "systemd":
    if r["linger"] is False:
        print("NOTE: couldn't enable lingering — timers only run while you're logged in;")
        print("      punches missed while logged out run at your next login.")
    print("Verify with:  systemctl --user list-timers 'keka-*'")
else:
    print("Verify with:  crontab -l")
print(f"Logs in:      {os.path.dirname(log)}/")
PYEOF
