"""
keka_check.py — reauth watchdog (run every ~6h + at login by the scheduler).

Keka's "remember this device" cookie (which lets us skip the OTP) lasts ~14
days. Ordinary session re-saves do NOT extend it; only a full password relogin
mints a fresh one — so when the saved session stays healthy for two straight
weeks (no relogin ever needed), the cookie quietly runs out anyway. This script
checks the cookie's expiry; if it's about to lapse it opens keka_setup.py (a
visible browser) and alerts you (notification + blocking dialog) so you can
enter the OTP. Otherwise it exits quietly — no browser, no interruption.

It must run FREQUENTLY: a once-daily check on a machine that happens to be
asleep at that hour can miss the whole warning window (this app once sailed
2 days past expiry that way).

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


# Shared with the punch scripts (they alert on failed punches the same way).
_ps_str = kc._ps_str


def _has_display():
    """True if a GUI is reachable. On headless Linux there's no browser/dialog."""
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True  # macOS/Windows GUI sessions always have a display


def notify(message):
    """Best-effort desktop notification — the shared keka_common implementation."""
    kc.notify(message, title=TITLE)


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
            import ctypes
            # MB_YESNO(0x04) | MB_ICONWARNING(0x30) | MB_SETFOREGROUND(0x10000)
            # SETFOREGROUND brings the box to front so it isn't lost behind windows.
            res = ctypes.windll.user32.MessageBoxW(
                0, message + "\n\nOpen the login browser now?", title, 0x04 | 0x30 | 0x10000
            )
            return res == 6  # IDYES
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
    try:
        with open(kc.SESSION_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        return None
    for c in s.get("cookies", []):
        if c.get("name") == "Identity.TwoFactorRememberMe":
            exp = c.get("expires", -1)
            return exp if exp and exp > 0 else None
    return None


def launch_setup(log):
    # On a headless box there is no browser/dialog — don't crash Playwright.
    if not _has_display():
        log.error("No display detected — cannot open the login browser. "
                  "SSH in and run:  python keka_setup.py  to renew the session.")
        return
    notify("Keka needs a quick re-login — please enter the OTP.")
    proceed = confirm_dialog(
        "Keka needs a quick re-login to keep auto-attendance working.\n\n"
        "A browser will open — please enter the OTP sent to your email/mobile."
    )
    if not proceed:
        log.info("User chose 'Remind me later' — will re-prompt on the next check")
        return
    # sys.executable is the venv python already running this script — portable
    # across .venv/bin/python (Unix) and .venv\Scripts\python.exe (Windows).
    py    = sys.executable
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
