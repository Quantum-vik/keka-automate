r"""
keka_doctor.py — one-shot health check for the whole installation.

    .venv/bin/python keka_doctor.py        # Windows: .venv\Scripts\python

The desktop-app equivalent of a service's /health endpoint: verifies every
layer the automation depends on and prints a ✓/✗ report. Exit code 0 means
"punches will work right now"; 1 means at least one required check failed.
Read-only — it never launches a browser or touches Keka.
"""

import os
import sys
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keka_common as kc
import license as lic

OK, BAD, WARN = "✓", "✗", "!"


def _report(mark, label, detail=""):
    print(f"  {mark}  {label:<28} {detail}")


def _schedule_installed():
    """Best-effort: is the OS-level punch schedule present? None = can't tell."""
    try:
        if sys.platform == "darwin":
            la = os.path.expanduser("~/Library/LaunchAgents")
            return all(os.path.exists(os.path.join(la, f"com.keka.{n}.plist"))
                       for n in ("punchin", "punchout"))
        if sys.platform.startswith("linux"):
            return kc.linux_schedule_method() is not None
        if sys.platform.startswith("win"):
            r = subprocess.run(["schtasks", "/Query", "/TN", r"Keka\PunchIn"],
                               capture_output=True, text=True)
            return r.returncode == 0
    except Exception:
        pass
    return None


def _native_window_backend():
    """Linux: can pywebview draw its WebKitGTK window from this interpreter?
    Returns e.g. 'WebKit2 4.1', or None (the UI then opens in the browser).
    Only resolves GObject typelibs — never opens a window."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
    except (ImportError, ValueError):
        return None
    for v in ("4.1", "4.0"):
        try:
            gi.require_version("WebKit2", v)
            return f"WebKit2 {v}"
        except ValueError:
            continue
    return None


def main():
    print(f"Auto-Keka doctor — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  data dir: {kc.DATA_DIR}\n")
    failures = 0

    # 1) heavy dependencies
    tess = kc._find_tesseract()
    if tess:
        _report(OK, "tesseract (captcha OCR)", tess)
    else:
        _report(BAD, "tesseract (captcha OCR)", "not found — run setup (--phase heavy)")
        failures += 1
    if kc.chromium_installed():
        _report(OK, "Playwright Chromium", "exact build present")
    else:
        _report(BAD, "Playwright Chromium",
                "missing/stale — run: python -m playwright install chromium")
        failures += 1
    if sys.platform.startswith("linux"):     # non-fatal: the browser fallback works
        gtk = _native_window_backend()
        if gtk:
            _report(OK, "native window (GTK)", gtk)
        else:
            _report(WARN, "native window (GTK)",
                    "unavailable — UI opens in your browser; run: ./setup.sh --phase heavy")

    # 2) configuration
    env = kc._load_env()
    if env.get("KEKA_EMAIL") and env.get("KEKA_PASSWORD"):
        _report(OK, "credentials (.env)", kc.ENV_FILE)
    else:
        _report(BAD, "credentials (.env)", f"KEKA_EMAIL/KEKA_PASSWORD unset in {kc.ENV_FILE}")
        failures += 1
    url = env.get("KEKA_BASE_URL", "")
    if url and "<company-name>" not in url:
        _report(OK, "Keka URL", url)
    else:
        _report(BAD, "Keka URL", "KEKA_BASE_URL not configured")
        failures += 1

    # 3) session health — real token expiry, no wall-clock guessing
    h = kc.session_health()
    if not h["exists"]:
        _report(BAD, "session", "no session.json — sign in from the app or keka_setup.py")
        failures += 1
    elif h["alive"] is True:
        left = (h["token_exp"] - h["checked_at"]) / 3600
        _report(OK, "session token", f"valid ({left:.1f}h left on the access token)")
    elif h["alive"] is False:
        _report(BAD, "session token", "EXPIRED — use 'Sign in again' in the app")
        failures += 1
    else:
        _report(WARN, "session token", "present but no token found — state unknown")
    if h["remember_valid"] is True:
        days = (h["remember_exp"] - h["checked_at"]) / 86400
        _report(OK, "device pass (2FA skip)", f"{days:.1f} days left")
    elif h["remember_valid"] is False:
        _report(WARN, "device pass (2FA skip)", "expired — next sign-in will ask for an OTP")
    else:
        _report(WARN, "device pass (2FA skip)", "not found")

    # 4) schedule + license (non-fatal context)
    sched = _schedule_installed()
    if sched is True:
        how = ""
        if sys.platform.startswith("linux"):
            how = {"systemd": " · catches up on wake", "cron": " · cron, on time only"}.get(
                kc.linux_schedule_method(), "")
        _report(OK, "punch schedule", f"installed (in {env.get('KEKA_IN_TIME', '09:00')}, "
                                      f"out {env.get('KEKA_OUT_TIME', '18:00')}, Mon-Fri{how})")
    elif sched is False:
        _report(WARN, "punch schedule", "not installed — apply it from Settings")
    else:
        _report(WARN, "punch schedule", "could not determine")
    info = lic.license_info()
    if info:
        _report(OK, "license", f"licensed to {info.get('n', '?')}")
    else:
        _report(WARN, "license", "no valid license key stored")

    print()
    if failures:
        print(f"{failures} required check(s) failed — punches will NOT work until fixed.")
        return 1
    print("All required checks passed — automation is healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
