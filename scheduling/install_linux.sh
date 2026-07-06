#!/usr/bin/env bash
#
# Install Keka auto-attendance schedule on Linux (cron).
#   bash scheduling/install_linux.sh
#
# Punch jobs are headless. The reauth watchdog opens a browser + dialog, so it
# needs your graphical session — we pass DISPLAY so cron can reach your desktop.
set -e

KEKA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$KEKA/.venv/bin/python"
DISP="${DISPLAY:-:0}"

if [ ! -x "$PY" ]; then
    echo "ERROR: $PY not found. Create the venv first:"
    echo "  python3 -m venv $KEKA/.venv && $KEKA/.venv/bin/pip install -r $KEKA/requirements.txt"
    echo "  $PY -m playwright install chromium"
    exit 1
fi

CRON_IN="0 9 * * 1-5 $PY $KEKA/keka_punch_in.py"
CRON_OUT="0 18 * * 1-5 $PY $KEKA/keka_punch_out.py"
CRON_CHK="0 10 * * * DISPLAY=$DISP $PY $KEKA/keka_check.py"

( crontab -l 2>/dev/null | grep -v "keka_punch\|keka_check"; \
  echo "$CRON_IN"; echo "$CRON_OUT"; echo "$CRON_CHK" ) | crontab -

echo "Installed Keka cron jobs:"
echo "  Punch in   9:00 AM Mon-Fri"
echo "  Punch out  6:00 PM Mon-Fri"
echo "  Reauth     10:00 AM daily (DISPLAY=$DISP)"
echo "Verify with:  crontab -l"
echo "Logs in:      $KEKA/logs/"
