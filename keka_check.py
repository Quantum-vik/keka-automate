"""
keka_check.py — reauth watchdog (run daily + at login by the scheduler).

Keka's "remember this device" cookie (which lets us skip the OTP) lasts ~14 days
and does NOT refresh on auto-relogin. So roughly every 14 days a real OTP is
needed. This script checks that cookie's expiry; if it's about to lapse it opens
keka_setup.py (a visible browser) and alerts you (notification + blocking dialog)
so you can enter the OTP. Otherwise it exits quietly — no browser, no interruption.

Notifications and the dialog work on macOS, Linux, and Windows.
"""

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keka_common as kc

BUFFER_DAYS = 1.5  # prompt this many days before the remember-cookie expires
TITLE = "Keka Attendance"


def notify(message):
    """Best-effort desktop notification (non-blocking). Silent if unsupported."""
    plat = sys.platform
    try:
        if plat == "darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{TITLE}" sound name "Glass"'],
                check=False,
            )
        elif plat.startswith("linux"):
            if shutil.which("notify-send"):
                subprocess.run(["notify-send", TITLE, message], check=False)
        elif plat.startswith("win"):
            # PowerShell balloon tip — no external deps
            ps = (
                'Add-Type -AssemblyName System.Windows.Forms;'
                '$n=New-Object System.Windows.Forms.NotifyIcon;'
                '$n.Icon=[System.Drawing.SystemIcons]::Information;'
                '$n.BalloonTipTitle=' + repr(TITLE) + ';'
                '$n.BalloonTipText=' + repr(message) + ';'
                '$n.Visible=$true;$n.ShowBalloonTip(10000);Start-Sleep -Seconds 6;'
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
    except Exception:
        pass


def confirm_dialog(message):
    """
    Blocking pop-up that stays on screen until the user clicks a button.
    Returns True to open the browser now, False for "Remind me later".
    Falls back across native dialog → tkinter so it works on every OS.
    """
    plat = sys.platform
    title = "Keka Attendance — Action Needed"
    try:
        if plat == "darwin":
            script = (
                f'display dialog "{message}" with title "{title}" '
                'buttons {"Remind me later", "Open now"} '
                'default button "Open now" with icon caution'
            )
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return "Open now" in (r.stdout or "")
        if plat.startswith("linux") and shutil.which("zenity"):
            r = subprocess.run(
                ["zenity", "--question", "--title", title, "--text", message,
                 "--ok-label=Open now", "--cancel-label=Remind me later"]
            )
            return r.returncode == 0
        if plat.startswith("win"):
            import ctypes  # MessageBoxW: 4=YesNo, 0x30=warning icon; 6=Yes
            res = ctypes.windll.user32.MessageBoxW(
                0, message + "\n\nOpen the login browser now?", title, 0x04 | 0x30
            )
            return res == 6
    except Exception:
        pass

    # Universal fallback: tkinter (stdlib, cross-platform)
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        ans = messagebox.askyesno(title, message + "\n\nOpen the login browser now?")
        root.destroy()
        return bool(ans)
    except Exception:
        return True  # can't ask (no GUI) → proceed and open setup


def remember_cookie_expiry():
    """Unix ts when Identity.TwoFactorRememberMe expires, or None if absent."""
    if not os.path.exists(kc.SESSION_FILE):
        return None
    with open(kc.SESSION_FILE) as f:
        s = json.load(f)
    for c in s.get("cookies", []):
        if c["name"] == "Identity.TwoFactorRememberMe":
            exp = c.get("expires", -1)
            return exp if exp and exp > 0 else None
    return None


def launch_setup(log):
    notify("Keka needs a quick re-login — please enter the OTP.")
    proceed = confirm_dialog(
        "Keka needs a quick re-login to keep auto-attendance working.\\n\\n"
        "A browser will open — please enter the OTP sent to your email/mobile."
    )
    if not proceed:
        log.info("User chose 'Remind me later' — will re-prompt on the next check")
        return
    py    = os.path.join(kc.SCRIPT_DIR, ".venv", "bin", "python")
    setup = os.path.join(kc.SCRIPT_DIR, "keka_setup.py")
    log.info("Launching interactive setup: %s %s", py, setup)
    subprocess.run([py, setup], check=False)


def main():
    log = kc.get_logger(kc.log_path("keka_reauth.log"))
    log.info("=== Keka reauth check ===")

    exp = remember_cookie_expiry()
    now = datetime.now().timestamp()

    if exp is None:
        log.info("No remember-device cookie found — interactive setup needed")
        launch_setup(log)
        return

    days_left = (exp - now) / 86400
    log.info("Remember-device cookie: %.2f days left (expires %s)",
             days_left, datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M"))

    if days_left > BUFFER_DAYS:
        log.info("Still valid — nothing to do")
        return

    log.info("Cookie near expiry — opening interactive setup")
    launch_setup(log)


if __name__ == "__main__":
    main()
