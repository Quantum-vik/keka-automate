#!/usr/bin/env bash
#
# Install Keka auto-attendance schedule on macOS (launchd LaunchAgents).
#   bash scheduling/install_macos.sh
#
# Generates the three LaunchAgents from THIS checkout's path and loads them.
# launchd runs missed jobs on wake and runs in your GUI session (needed so the
# reauth browser can appear). No Full Disk Access required.
set -e

KEKA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$KEKA/.venv/bin/python"
LA="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
mkdir -p "$LA" "$KEKA/logs"

if [ ! -x "$PY" ]; then
    echo "ERROR: $PY not found. Create the venv first:"
    echo "  python3 -m venv $KEKA/.venv && $KEKA/.venv/bin/pip install -r $KEKA/requirements.txt"
    echo "  $PY -m playwright install chromium"
    exit 1
fi

# $1=label  $2=script  $3=logname  $4=calendar-block  $5=extra-keys
make_plist() {
    local label="$1" script="$2" logname="$3" cal="$4" extra="$5"
    cat > "$LA/$label.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$label</string>
    <key>ProgramArguments</key>
    <array><string>$PY</string><string>$KEKA/$script</string></array>
    <key>StartCalendarInterval</key>
    $cal
    $extra
    <key>EnvironmentVariables</key>
    <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
    <key>StandardOutPath</key><string>$KEKA/logs/$logname</string>
    <key>StandardErrorPath</key><string>$KEKA/logs/$logname</string>
</dict>
</plist>
PLIST
}

weekdays() {  # $1=hour
    local h="$1" out=""
    for d in 1 2 3 4 5; do
        out+="<dict><key>Weekday</key><integer>$d</integer><key>Hour</key><integer>$h</integer><key>Minute</key><integer>0</integer></dict>"
    done
    echo "<array>$out</array>"
}

make_plist "com.keka.punchin"  "keka_punch_in.py"  "keka_punch_in.log"  "$(weekdays 9)"  ""
make_plist "com.keka.punchout" "keka_punch_out.py" "keka_punch_out.log" "$(weekdays 18)" ""
make_plist "com.keka.reauth"   "keka_check.py"     "keka_reauth.log" \
    "<dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>" \
    "<key>RunAtLoad</key><true/>"

for f in punchin punchout reauth; do
    launchctl bootout   "gui/$UID_NUM/com.keka.$f" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_NUM" "$LA/com.keka.$f.plist"
    echo "loaded com.keka.$f"
done

echo "Done. Status:  launchctl list | grep keka"
echo "Logs in:      $KEKA/logs/"
