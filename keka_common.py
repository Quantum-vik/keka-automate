"""
Keka automation — shared logic.

Design (works around Keka's captcha + 2FA):

  1. keka_setup.py  → run ONCE interactively. Does captcha login, you enter the
     OTP once, then the authenticated session is saved to session.json. Keka
     also drops a "TwoFactorRememberMe" cookie good for ~14 days.

  2. keka_punch_in.py / keka_punch_out.py → run by cron. They load session.json
     and click punch. If the session has expired, they AUTO-RELOGIN with
     password + OCR-captcha only (no OTP, thanks to the remember-device cookie)
     and re-save the session. Only when the remember-device cookie itself
     expires (~14 days) do they exit(1) asking you to re-run keka_setup.py.
"""

import os
import sys
import glob
import json
import time
import shutil
import base64
import logging
import tempfile
import subprocess
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image
import pytesseract
from playwright.sync_api import sync_playwright

# ── tesseract discovery (cross-platform) ──────────────────────────────────────
# Prefer whatever is on PATH; otherwise probe the standard per-OS install dirs.
# Needed because schedulers (launchd/cron/Task Scheduler) run with a minimal PATH.
def _find_tesseract():
    onpath = shutil.which("tesseract")
    if onpath:
        return onpath
    candidates = [
        "/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract",   # macOS
        "/usr/bin/tesseract",                                        # Linux
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",             # Windows
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

_tess = _find_tesseract()
if _tess:
    pytesseract.pytesseract.tesseract_cmd = _tess

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Single source of truth for the app version. release.yml reads THIS for the
# Nuitka product-version, and the in-app update check compares it against the
# latest GitHub release tag — so bumping this one line is what a release needs.
APP_VERSION = "1.0.5"
GITHUB_REPO = "Quantum-vik/keka-automate"

# True when running as a Nuitka-compiled binary (no source tree, no venv).
# Frozen mode dispatches punches through `<binary> --punch` and installs the
# schedule natively instead of via the repo's shell scripts.
FROZEN = "__compiled__" in globals()


def _app_data_dir():
    """A STABLE per-user folder for our data (.env, session, license, logs).

    Crucial for the compiled one-file build: Nuitka unpacks the binary to a
    throwaway temp dir each launch, so anything stored next to the code would be
    lost between runs. A proper OS app-data folder persists.
    """
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    d = os.path.join(base, "Auto-Keka")
    os.makedirs(d, exist_ok=True)
    return d


DATA_DIR     = _app_data_dir()
SESSION_FILE = os.path.join(DATA_DIR, "session.json")
SESSION_LOCK_FILE = os.path.join(DATA_DIR, "session.lock")
TIMEOFF_FILE = os.path.join(DATA_DIR, "timeoff.json")
PAUSE_FILE   = os.path.join(DATA_DIR, "paused.flag")
ENV_FILE     = os.path.join(DATA_DIR, ".env")
LOG_DIR      = os.path.join(DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def _migrate_legacy():
    """One-time move of files from the old 'next to the code' layout into
    DATA_DIR, so existing users (and their running scheduler) keep working."""
    for name, dest in ((".env", ENV_FILE), ("session.json", SESSION_FILE),
                       ("license.key", os.path.join(DATA_DIR, "license.key"))):
        legacy = os.path.join(SCRIPT_DIR, name)
        if os.path.exists(legacy) and not os.path.exists(dest):
            try:
                shutil.copy2(legacy, dest)
                os.chmod(dest, 0o600)
            except OSError:
                pass


_migrate_legacy()


def log_path(name):
    return os.path.join(LOG_DIR, name)

# Transient screenshots go to the OS temp dir (they're auto-cleaned each run).
TMP_DIR = tempfile.gettempdir()
def tmp_path(name):
    return os.path.join(TMP_DIR, name)


def _load_env():
    """Parse DATA_DIR/.env (KEY=VALUE lines) into a dict. Real env vars win."""
    values = {}
    env_path = ENV_FILE
    if os.path.exists(env_path):
        # utf-8-sig transparently strips a UTF-8 BOM (Windows editors/PowerShell
        # add one), which would otherwise corrupt the first key name.
        with open(env_path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def _apply_env(values):
    """Set the module-level config from a parsed .env dict + real env vars."""
    global BASE_URL, TENANT_HOST, ATTENDANCE_URL, EMAIL, PASSWORD, IN_TIME, OUT_TIME
    BASE_URL = os.environ.get("KEKA_BASE_URL") or values.get("KEKA_BASE_URL") or "https://<company-name>.keka.com"
    TENANT_HOST = BASE_URL.split("://")[-1].split("/")[0]
    ATTENDANCE_URL = f"{BASE_URL}/#/me/attendance/logs"
    EMAIL = os.environ.get("KEKA_EMAIL") or values.get("KEKA_EMAIL") or ""
    PASSWORD = os.environ.get("KEKA_PASSWORD") or values.get("KEKA_PASSWORD") or ""
    IN_TIME = values.get("KEKA_IN_TIME", "09:00")
    OUT_TIME = values.get("KEKA_OUT_TIME", "18:00")


_env = _load_env()
_apply_env(_env)


def reload_config():
    """Re-read .env into the module globals (call after the GUI edits it)."""
    global _env
    _env = _load_env()
    _apply_env(_env)


def update_env(updates):
    """Merge {KEY: value} into .env (create if missing), keep other keys, 0600."""
    current = _load_env()
    for k, v in updates.items():
        if v is not None:
            current[str(k)] = str(v)
    env_path = ENV_FILE
    tmp_path = env_path + ".tmp"
    lines = ["# Keka credentials + settings. Private — keep chmod 600."]
    lines += [f"{k}={v}" for k, v in current.items()]
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(tmp_path, 0o600)
    except OSError:
        pass
    os.replace(tmp_path, env_path)
    reload_config()
# ─────────────────────────────────────────────────────────────────────────────


# ── Dependency readiness (for the self-bootstrapping app) ─────────────────────
# The app opens as soon as the LIGHT deps (pip packages) exist, then installs
# the HEAVY deps (Chromium + tesseract) in the background. These helpers let the
# UI know whether the heavy deps are present yet.
def _playwright_browsers_dir():
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override and override != "0":
        return override
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Caches", "ms-playwright")
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(base, "ms-playwright")
    return os.path.join(home, ".cache", "ms-playwright")


_chromium_ok = None   # cache: once the right build is seen it can't un-install mid-run


def chromium_installed():
    """True if the EXACT Chromium build this Playwright version needs exists.
    Merely finding a chromium-* folder is not enough — after a playwright
    upgrade a stale build lingers there while launches fail with
    'Executable doesn't exist'. Ask Playwright for the real executable path."""
    global _chromium_ok
    if _chromium_ok:
        return True
    try:
        with sync_playwright() as p:
            _chromium_ok = os.path.exists(p.chromium.executable_path)
    except Exception:
        d = _playwright_browsers_dir()   # driver unavailable — fall back to a dir probe
        _chromium_ok = os.path.isdir(d) and any(
            n.startswith(("chromium-", "chromium_headless_shell-")) for n in os.listdir(d))
    return _chromium_ok


def deps_ready():
    """True when the heavy deps (Chromium + tesseract OCR) are both present."""
    return bool(_find_tesseract()) and chromium_installed()


def install_chromium_frozen():
    """Download Playwright's Chromium from a compiled binary. There is no venv
    to run 'python -m playwright install', so drive the bundled node driver CLI
    directly. Blocking (can take minutes) → bool."""
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        driver = compute_driver_executable()
        cmd = list(driver) if isinstance(driver, (tuple, list)) else [str(driver)]
        r = subprocess.run(cmd + ["install", "chromium"], env=get_driver_env(),
                           capture_output=True, text=True, timeout=1800)
        global _chromium_ok
        _chromium_ok = None          # force a re-probe after the download
        return r.returncode == 0
    except Exception:
        return False


# ── First-run onboarding flag ─────────────────────────────────────────────────
def is_onboarded():
    return _load_env().get("KEKA_ONBOARDED", "") == "1"


def mark_onboarded():
    update_env({"KEKA_ONBOARDED": "1"})


# ── Auto-open at login (cross-platform) ───────────────────────────────────────
def _venv_python(windowless=False):
    """Path to the repo's venv interpreter (falls back to the current one)."""
    if sys.platform.startswith("win"):
        scripts = os.path.join(SCRIPT_DIR, ".venv", "Scripts")
        if windowless:
            pw = os.path.join(scripts, "pythonw.exe")
            if os.path.exists(pw):
                return pw
        p = os.path.join(scripts, "python.exe")
        return p if os.path.exists(p) else sys.executable
    p = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")
    return p if os.path.exists(p) else sys.executable


def macos_app_bundle():
    """Path to an installed Auto-Keka.app, or None. Preferring the bundle for
    launches gives the process a real Dock identity (name + icon) instead of
    showing as 'python3.13'."""
    for p in ("/Applications/Auto-Keka.app",
              os.path.expanduser("~/Applications/Auto-Keka.app"),
              os.path.join(SCRIPT_DIR, "Auto-Keka.app")):
        if os.path.isdir(p):
            return p
    return None


def install_autostart():
    """Launch the Auto-Keka window automatically at login. Best-effort → bool."""
    ui = os.path.join(SCRIPT_DIR, "keka_ui.py")
    try:
        if sys.platform == "darwin":
            app = macos_app_bundle()
            if FROZEN and ".app/" in sys.executable:
                app = sys.executable.split(".app/", 1)[0] + ".app"
            if app:
                # Launch through LaunchServices so the Dock shows the app
                # bundle's name and icon, not the python interpreter's.
                prog = ('<string>/usr/bin/open</string>'
                        f'<string>-a</string><string>{app}</string>')
            elif FROZEN:
                prog = f'<string>{sys.executable}</string>'
            else:
                prog = f'<string>{_venv_python()}</string><string>{ui}</string>'
            la = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(la, exist_ok=True)
            plist = os.path.join(la, "com.keka.app.plist")
            with open(plist, "w", encoding="utf-8") as f:
                f.write(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>Label</key><string>com.keka.app</string>\n'
                    f'  <key>ProgramArguments</key><array>{prog}</array>\n'
                    '  <key>RunAtLoad</key><true/>\n'
                    '  <key>ProcessType</key><string>Interactive</string>\n'
                    '</dict></plist>\n'
                )
            subprocess.run(["launchctl", "unload", plist], capture_output=True)
            subprocess.run(["launchctl", "load", plist], capture_output=True)
            return True
        if sys.platform.startswith("linux"):
            cmd = sys.executable if FROZEN else f"{_venv_python()} {ui}"
            ad = os.path.expanduser("~/.config/autostart")
            os.makedirs(ad, exist_ok=True)
            with open(os.path.join(ad, "auto-keka.desktop"), "w", encoding="utf-8") as f:
                f.write(
                    "[Desktop Entry]\nType=Application\nName=Auto-Keka\n"
                    f"Exec={cmd}\nX-GNOME-Autostart-enabled=true\nTerminal=false\n"
                )
            return True
        if sys.platform.startswith("win"):
            import winreg
            val = (f'"{sys.executable}"' if FROZEN
                   else f'"{_venv_python(windowless=True)}" "{ui}"')
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "AutoKeka", 0, winreg.REG_SZ, val)
            winreg.CloseKey(key)
            return True
    except Exception:
        return False
    return False


def remove_autostart():
    """Undo install_autostart(). Best-effort → bool."""
    try:
        if sys.platform == "darwin":
            plist = os.path.expanduser("~/Library/LaunchAgents/com.keka.app.plist")
            subprocess.run(["launchctl", "unload", plist], capture_output=True)
            if os.path.exists(plist):
                os.remove(plist)
            return True
        if sys.platform.startswith("linux"):
            f = os.path.expanduser("~/.config/autostart/auto-keka.desktop")
            if os.path.exists(f):
                os.remove(f)
            return True
        if sys.platform.startswith("win"):
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, "AutoKeka")
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
            return True
    except Exception:
        return False
    return False
def _parse_hhmm(s, dh, dm):
    try:
        h, m = str(s).strip().split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        return dh, dm


def install_schedule_native(in_time="09:00", out_time="18:00"):
    """FROZEN-mode scheduler: register Mon-Fri punch jobs that invoke THIS
    binary with --punch (the shell installers assume a source checkout + venv,
    which a compiled distribution doesn't have). Best-effort → bool."""
    exe = sys.executable
    ih, im = _parse_hhmm(in_time, 9, 0)
    oh, om = _parse_hhmm(out_time, 18, 0)
    try:
        if sys.platform == "darwin":
            la = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(la, exist_ok=True)
            uid = os.getuid()
            for label, action, h, m in (("com.keka.punchin", "in", ih, im),
                                        ("com.keka.punchout", "out", oh, om)):
                cal = "".join(
                    f"<dict><key>Weekday</key><integer>{d}</integer>"
                    f"<key>Hour</key><integer>{h}</integer>"
                    f"<key>Minute</key><integer>{m}</integer></dict>" for d in range(1, 6))
                plist = os.path.join(la, f"{label}.plist")
                with open(plist, "w", encoding="utf-8") as f:
                    f.write(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        f'  <key>Label</key><string>{label}</string>\n'
                        '  <key>ProgramArguments</key><array>'
                        f'<string>{exe}</string><string>--punch</string><string>{action}</string></array>\n'
                        f'  <key>StartCalendarInterval</key><array>{cal}</array>\n'
                        f'  <key>StandardOutPath</key><string>{log_path(f"keka_punch_{action}.log")}</string>\n'
                        f'  <key>StandardErrorPath</key><string>{log_path(f"keka_punch_{action}.log")}</string>\n'
                        '</dict></plist>\n')
                subprocess.run(["launchctl", "bootout", f"gui/{uid}/{label}"],
                               capture_output=True)
                subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", plist],
                               capture_output=True)
            return True
        if sys.platform.startswith("linux"):
            cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            keep = [l for l in (cur.stdout or "").splitlines()
                    if "--punch" not in l and "keka_punch" not in l]
            log = log_path("cron.log")
            keep.append(f"{im} {ih} * * 1-5 {exe} --punch in >> {log} 2>&1")
            keep.append(f"{om} {oh} * * 1-5 {exe} --punch out >> {log} 2>&1")
            r = subprocess.run(["crontab", "-"], input="\n".join(keep) + "\n",
                               capture_output=True, text=True)
            return r.returncode == 0
        if sys.platform.startswith("win"):
            ok = True
            for name, action, t in (("PunchIn", "in", f"{ih:02d}:{im:02d}"),
                                    ("PunchOut", "out", f"{oh:02d}:{om:02d}")):
                r = subprocess.run(
                    ["schtasks", "/Create", "/F", "/TN", rf"Keka\{name}",
                     "/SC", "WEEKLY", "/D", "MON,TUE,WED,THU,FRI",
                     "/TR", f'"{exe}" --punch {action}', "/ST", t],
                    capture_output=True)
                ok = ok and r.returncode == 0
            return ok
    except Exception:
        return False
    return False


def desktop_app_installed():
    """Is the OS-native app wrapper (bundle / shortcut / .desktop) in place?"""
    if sys.platform == "darwin":
        return macos_app_bundle() is not None
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", "")
        lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                           "Programs", "Auto-Keka.lnk")
        return os.path.exists(lnk)
    return os.path.exists(os.path.expanduser(
        "~/.local/share/applications/auto-keka.desktop"))


def install_desktop_app():
    """Build + install the native app wrapper for this OS, so users launch
    'Auto-Keka' with an icon — never a python file. Best-effort → bool.

    macOS: assemble Auto-Keka.app and copy it to /Applications (or
    ~/Applications). Windows: Desktop + Start Menu shortcuts (icon, hidden
    console). Linux: ~/.local/share .desktop entry + icon."""
    pack = os.path.join(SCRIPT_DIR, "packaging")
    try:
        if sys.platform == "darwin":
            subprocess.run(["bash", os.path.join(pack, "build_macos_app.sh")],
                           capture_output=True, timeout=180)
            src = os.path.join(SCRIPT_DIR, "Auto-Keka.app")
            if not os.path.isdir(src):
                return False
            for dest_dir in ("/Applications", os.path.expanduser("~/Applications")):
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                    dest = os.path.join(dest_dir, "Auto-Keka.app")
                    if os.path.isdir(dest):
                        shutil.rmtree(dest)
                    shutil.copytree(src, dest, symlinks=True)
                    return True
                except OSError:
                    continue
            return False
        if sys.platform.startswith("win"):
            r = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", os.path.join(pack, "build_windows_app.ps1")],
                capture_output=True, timeout=180)
            return r.returncode == 0
        r = subprocess.run(["bash", os.path.join(pack, "build_linux_app.sh")],
                           capture_output=True, timeout=180)
        return r.returncode == 0
    except Exception:
        return False
# ─────────────────────────────────────────────────────────────────────────────


def get_logger(log_file):
    # File handler always; console handler only for interactive runs. Under
    # launchd/cron, stdout is already redirected to the log file, so adding a
    # StreamHandler there would double every line.
    handlers = [logging.FileHandler(log_file, encoding="utf-8")]
    if sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger("keka")


# ── Captcha OCR ───────────────────────────────────────────────────────────────
def ocr_captcha(page):
    """Extract captcha text from the #imgCaptcha base64 PNG using tesseract."""
    img_src = page.get_attribute("#imgCaptcha", "src") or ""
    if "base64," not in img_src:
        return ""
    b64_data = img_src.split("base64,", 1)[1]

    # Captcha PNG has a transparent background — composite onto white first
    raw = Image.open(BytesIO(base64.b64decode(b64_data))).convert("RGBA")
    white = Image.new("RGBA", raw.size, (255, 255, 255, 255))
    white.paste(raw, mask=raw.split()[3])
    rgb = white.convert("RGB")

    # Binarize: any non-white pixel (any channel < 230) becomes black text
    pixels = rgb.load()
    w, h = rgb.size
    bw = Image.new("L", (w, h), 255)
    bw_px = bw.load()
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            if r < 230 or g < 230 or b < 230:
                bw_px[x, y] = 0

    # Scale up 4x — improves tesseract accuracy on small captchas
    bw = bw.resize((bw.width * 4, bw.height * 4), Image.NEAREST)

    text = pytesseract.image_to_string(
        bw,
        config="--psm 7 --oem 1 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    ).strip()
    return "".join(text.split())


# ── Login helpers ─────────────────────────────────────────────────────────────
def goto_login_form(page, log):
    """Navigate to Keka and click 'Continue with Password' to reveal the form."""
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(2500)
    page.locator('button:has-text("Continue with Password")').first.click()
    page.wait_for_selector("#imgCaptcha", timeout=10_000)
    page.wait_for_timeout(500)
    log.info("Login form visible")


CAPTCHA_LEN = 5  # Keka captchas are always exactly 5 alphanumeric chars


def submit_credentials(page, log, max_attempts=12):
    """
    Fill email/password/captcha and submit, retrying the captcha until the
    login is accepted. Returns the URL after a successful password step
    (which for this tenant is the 2FA 'SendCode' page), or None on failure.
    """
    goto_login_form(page, log)

    for attempt in range(1, max_attempts + 1):
        captcha_text = ocr_captcha(page)
        log.info("Captcha OCR attempt %d: '%s'", attempt, captcha_text)

        # Captchas are always 5 chars — a different length means a bad OCR read,
        # so skip submitting (which would just waste a rejection) and reload.
        if len(captcha_text) != CAPTCHA_LEN:
            log.warning("OCR length %d != %d — reloading captcha", len(captcha_text), CAPTCHA_LEN)
            goto_login_form(page, log)
            continue

        page.fill("#email", EMAIL)
        page.fill("#password", PASSWORD)
        page.fill("#captcha", captcha_text)
        page.locator('button:has-text("Login")').first.click()
        page.wait_for_timeout(3000)

        url = page.url
        # Wrong captcha keeps us on the KekaLogin page; a correct one advances
        # to SendCode (2FA) or straight into the app.
        if "KekaLogin" in url:
            log.warning("Captcha rejected (attempt %d), retrying...", attempt)
            goto_login_form(page, log)
            continue

        log.info("Password step accepted — URL: %s", url)
        return url

    log.error("Failed password login after %d captcha attempts", max_attempts)
    return None


def is_logged_in(page):
    """True if the current page is inside the authenticated app (not the login)."""
    url = page.url
    return TENANT_HOST in url and "app.keka.com" not in url and "Account" not in url


def save_session(ctx):
    """Persist the browser session, then lock the file to owner-only (0600).
    session.json holds auth cookies, so it must not be world-readable.
    Written to a tmp file and renamed into place so a crash mid-write can't
    corrupt an existing session."""
    tmp = SESSION_FILE + ".tmp"
    ctx.storage_state(path=tmp)
    try:
        os.chmod(tmp, 0o600)   # no-op-ish on Windows, harmless
    except OSError:
        pass
    os.replace(tmp, SESSION_FILE)


# ── Cross-process session lock ────────────────────────────────────────────────
# The UI app, the punch scripts, and the reauth setup all run load→relogin→save
# in SEPARATE processes; an in-process threading.Lock can't stop two of them
# interleaving and letting the stale login's cookies win the last write. This
# lock serializes those sequences. It is advisory and best-effort: callers get
# None on timeout and PROCEED — a punch must never be skipped over a lock.

def _acquire_session_lock(timeout=120, log=None):
    """Take the cross-process session lock. Returns an open file handle to pass
    to _release_session_lock, or None if the lock stayed busy past timeout."""
    try:
        f = open(SESSION_LOCK_FILE, "a+")
    except OSError:
        return None
    deadline = time.time() + timeout
    while True:
        try:
            if sys.platform.startswith("win"):
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except OSError:
            if time.time() >= deadline:
                if log:
                    log.warning("session lock busy after %ss — proceeding without it",
                                timeout)
                f.close()
                return None
            time.sleep(1.5)


def _release_session_lock(f):
    if not f:
        return
    try:
        if sys.platform.startswith("win"):
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        pass
    f.close()


# ── UI-driven headless login (email OTP entered in the app, no browser popup) ──
def request_email_otp(page, log):
    """On the 2FA 'SendCode' page, ask Keka to email the OTP. No-op if we're
    already on the code-entry page."""
    if "SendCode" not in page.url:
        return True
    for sel in ('button:has-text("Send code to email")',
                'a:has-text("Send code to email")',
                'button:has-text("email")', 'a:has-text("email")'):
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            loc.first.click()
            page.wait_for_timeout(2500)
            log.info("Requested OTP to email")
            return True
    log.warning("'Send code to email' button not found")
    return False


def submit_otp(page, log, otp):
    """Fill the emailed OTP and submit. Returns True if login completes."""
    otp = "".join(str(otp).split())
    filled = False
    for sel in ('input[name="Code"]', 'input#Code', 'input[name*="code" i]',
                'input[id*="code" i]', 'input[placeholder*="code" i]',
                'input[type="tel"]', 'input[type="number"]',
                'input[type="text"]:not([type="hidden"])'):
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            loc.first.fill(otp)
            filled = True
            log.info("OTP entered")
            break
    if not filled:
        log.error("OTP input field not found")
        return False
    clicked = False
    for sel in ('button:has-text("Login")', 'button:has-text("Verify")',
                'button:has-text("Submit")', 'button:has-text("Confirm")',
                'button:has-text("Sign in")', 'button:has-text("Continue")',
                'button[type="submit"]'):
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            loc.first.click()
            clicked = True
            break
    if not clicked:
        page.keyboard.press("Enter")   # single-field form — Enter submits it
    page.wait_for_timeout(3500)
    return is_logged_in(page)


def interactive_login(otp_getter, log, headless=True):
    """
    Full login used by the GUI. Reuses the saved session if still valid;
    otherwise does password + OCR captcha, requests the email OTP, and calls
    otp_getter() (which blocks until the user types the code in the UI).

    otp_getter(retry=False) -> str|None   (None cancels)
    Returns True on success, False otherwise. Runs headless (no browser popup).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        # Locked from BEFORE the state load: relogin decisions made on a stale
        # snapshot must not overwrite cookies another process just refreshed.
        _lk = _acquire_session_lock(timeout=60, log=log)
        state = SESSION_FILE if os.path.exists(SESSION_FILE) else None
        ctx = browser.new_context(storage_state=state)
        page = ctx.new_page()
        try:
            # 1) reuse existing session if it still works
            page.goto(ATTENDANCE_URL, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(4000)
            if is_logged_in(page):
                save_session(ctx)
                log.info("Existing session still valid")
                return True

            # 2) password + captcha
            url = submit_credentials(page, log)
            if not url:
                return False

            # 3) OTP, if the tenant asks for it (it does)
            if "SendCode" in url or "VerifyCode" in url:
                request_email_otp(page, log)
                ok, tries = False, 0
                while not ok and tries < 3:
                    otp = otp_getter(retry=(tries > 0))
                    if not otp:
                        log.info("Login cancelled by user")
                        return False
                    ok = submit_otp(page, log, otp)
                    tries += 1
                if not ok:
                    log.error("OTP not accepted after %d tries", tries)
                    return False

            # 4) warm up attendance origin + save
            try:
                page.goto(ATTENDANCE_URL, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(4000)
            except Exception:
                pass
            save_session(ctx)
            log.info("Login complete — session saved")
            return True
        finally:
            _release_session_lock(_lk)
            browser.close()


# ── Desktop notifications (shared by the reauth watchdog and punch scripts) ──
def _ps_str(s):
    """Wrap s as a safe PowerShell single-quoted string literal ('' escapes ')."""
    return "'" + str(s).replace("'", "''") + "'"


def notify(message, title="Keka Attendance"):
    """Best-effort desktop notification (non-blocking). Silent if unsupported."""
    plat = sys.platform
    try:
        if plat == "darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}" sound name "Glass"'],
                check=False,
            )
        elif plat.startswith("linux"):
            if shutil.which("notify-send"):
                subprocess.run(["notify-send", title, message], check=False)
        elif plat.startswith("win"):
            # PowerShell tray balloon — load both assemblies, pump the message
            # queue (DoEvents) so the balloon actually renders, then dispose.
            ps = (
                'Add-Type -AssemblyName System.Windows.Forms;'
                'Add-Type -AssemblyName System.Drawing;'
                '$n=New-Object System.Windows.Forms.NotifyIcon;'
                '$n.Icon=[System.Drawing.SystemIcons]::Information;'
                '$n.BalloonTipTitle=' + _ps_str(title) + ';'
                '$n.BalloonTipText=' + _ps_str(message) + ';'
                '$n.Visible=$true;$n.ShowBalloonTip(5000);'
                '[System.Windows.Forms.Application]::DoEvents();'
                'Start-Sleep -Milliseconds 6000;$n.Dispose();'
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
    except Exception:
        pass


# ── Session history log (for the UI activity feed / "previous session info") ──
HISTORY_FILE = log_path("history.jsonl")


def log_history(kind, msg):
    """Append one activity/session event to logs/history.jsonl.
    kind: 'in' | 'out' | 'info'. Used by the punch scripts and the UI so you
    can always see previous clock-ins/outs and refreshes."""
    entry = {
        "ts": int(time.time() * 1000),
        "time": datetime.now().strftime("%H:%M"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": kind,
        "msg": msg,
    }
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        os.chmod(HISTORY_FILE, 0o600)
    except OSError:
        pass
    return entry


def read_history(n=200):
    """Return the last n history entries (oldest→newest)."""
    if not os.path.exists(HISTORY_FILE):
        return []
    out = []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        return []
    return out[-n:]


# ── Time off: holidays / planned leave — auto-punch skips these dates ─────────
# Stored as a small JSON list in DATA_DIR: [{date:"YYYY-MM-DD", kind, note}].
def _valid_date(s):
    try:
        datetime.strptime(str(s).strip(), "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def load_timeoff():
    """Return the saved time-off entries (list of dicts), oldest date first.
    Never raises — a missing/corrupt file yields []."""
    try:
        with open(TIMEOFF_FILE, encoding="utf-8") as f:
            data = json.load(f)
        entries = [e for e in data
                   if isinstance(e, dict) and _valid_date(e.get("date"))]
        entries.sort(key=lambda e: e["date"])
        return entries
    except (OSError, ValueError):
        return []


def save_timeoff(entries):
    """Validate, de-dupe by date, sort, and persist. Returns the cleaned list."""
    clean, seen = [], set()
    for e in entries or []:
        d = str((e or {}).get("date", "")).strip()
        if not _valid_date(d) or d in seen:
            continue
        seen.add(d)
        kind = (e.get("kind") or "leave").strip().lower()
        if kind not in ("leave", "holiday", "wfh"):
            kind = "leave"
        clean.append({"date": d, "kind": kind, "note": str(e.get("note") or "")[:80]})
    clean.sort(key=lambda e: e["date"])
    tmp = TIMEOFF_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f)
        os.replace(tmp, TIMEOFF_FILE)
    except OSError:
        pass
    return clean


def is_timeoff(date_str):
    """The matching time-off entry for a YYYY-MM-DD date, or None. Fail-open:
    any error returns None so a broken file can never block a real punch."""
    try:
        for e in load_timeoff():
            if e.get("date") == date_str:
                return e
    except Exception:
        pass
    return None


# ── Pause switch: auto-punch no-ops while paused (a user kill-switch) ──────────
def is_paused():
    """True if automation is paused. Fail-open: errors read as NOT paused, so a
    filesystem glitch never silently stops your punches."""
    try:
        return os.path.exists(PAUSE_FILE)
    except OSError:
        return False


def set_paused(paused):
    try:
        if paused:
            with open(PAUSE_FILE, "w", encoding="utf-8") as f:
                f.write(datetime.now().isoformat())
            os.chmod(PAUSE_FILE, 0o600)
        elif os.path.exists(PAUSE_FILE):
            os.remove(PAUSE_FILE)
        return True
    except OSError:
        return False


# ── Attendance stats + CSV export (derived from history.jsonl) ────────────────
def _hhmm_to_min(s):
    try:
        h, m = str(s).strip().split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def day_punches(history):
    """Collapse history into date -> {'in': first-in HH:MM, 'out': last-out HH:MM}."""
    days = {}
    for h in history or []:
        d, k, t = h.get("date"), h.get("kind"), h.get("time")
        if not d or k not in ("in", "out"):
            continue
        slot = days.setdefault(d, {"in": None, "out": None})
        if k == "in" and slot["in"] is None:
            slot["in"] = t
        elif k == "out":
            slot["out"] = t
    return days


def attendance_stats(history, schedule_in="09:00", now=None):
    """Worked-time rollups for the current ISO week and calendar month.
    Pure over (history, schedule_in, now). 5-minute grace before 'late'.
    Returns {"week": {...}, "month": {...}} with days/minutes/late each."""
    now = now or datetime.now()
    sched = _hhmm_to_min(schedule_in) or 540
    week_start = now.date() - timedelta(days=now.weekday())
    month_key = now.strftime("%Y-%m")
    week = {"days": 0, "minutes": 0, "late": 0}
    month = {"days": 0, "minutes": 0, "late": 0}
    for d, slot in day_punches(history).items():
        try:
            dd = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        in_m, out_m = _hhmm_to_min(slot["in"]), _hhmm_to_min(slot["out"])
        worked = out_m - in_m if (in_m is not None and out_m is not None and out_m > in_m) else 0
        present = in_m is not None
        late = present and in_m > sched + 5
        if week_start <= dd <= now.date():
            week["days"] += present
            week["minutes"] += worked
            week["late"] += late
        if d.startswith(month_key):
            month["days"] += present
            month["minutes"] += worked
            month["late"] += late
    return {"week": week, "month": month}


def history_to_csv(history):
    """One row per day: Date, Clock In, Clock Out, Worked (H:MM)."""
    import csv
    import io as _io
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Clock In", "Clock Out", "Worked"])
    for d in sorted(day_punches(history)):
        slot = day_punches(history)[d]
        in_m, out_m = _hhmm_to_min(slot["in"]), _hhmm_to_min(slot["out"])
        worked = ""
        if in_m is not None and out_m is not None and out_m > in_m:
            mins = out_m - in_m
            worked = f"{mins // 60}:{mins % 60:02d}"
        w.writerow([d, slot["in"] or "", slot["out"] or "", worked])
    return buf.getvalue()


def export_history_csv(dest_dir=None):
    """Write the full attendance history to a CSV. Prefers ~/Desktop, falls
    back to DATA_DIR. Returns the written path."""
    if not dest_dir:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        dest_dir = desktop if os.path.isdir(desktop) else DATA_DIR
    path = os.path.join(dest_dir, f"auto-keka-attendance-{datetime.now():%Y%m%d}.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(history_to_csv(read_history(1_000_000)))
    return path


# ── Update check (compare our version to the latest GitHub release) ───────────
# The Python analog of electron-updater: poll /releases/latest, semver-compare,
# and surface a "download" prompt. We do NOT self-replace the running binary
# (unsafe for a compiled one-file app) — we point the user at the release page.
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"


def _semver_tuple(s):
    """('1.2.10') -> (1, 2, 10). Missing/garbage parts become 0; a trailing
    pre-release suffix (1.2.0-rc.1) is dropped for the numeric compare."""
    core = str(s or "").strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = []
    for p in core.split(".")[:3]:
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _is_newer(candidate, current):
    """True if version string `candidate` is strictly newer than `current`."""
    return _semver_tuple(candidate) > _semver_tuple(current)


def check_for_update(current=None, timeout=6):
    """Ask GitHub for the latest NON-prerelease and compare to our version.
    Pure network read — never raises. Returns:
      {available, current, latest, url, notes}
    with available=False (and latest=None) on any error, no release, or when
    we're already current. Pre-releases are skipped (the release pipeline tags
    them with a '-' suffix and marks them prerelease)."""
    current = current or APP_VERSION
    out = {"available": False, "current": current, "latest": None,
           "url": RELEASES_PAGE, "notes": ""}
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"Auto-Keka/{current}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("prerelease") or data.get("draft"):
            return out
        tag = data.get("tag_name") or ""
        out["latest"] = tag.lstrip("vV")
        out["url"] = data.get("html_url") or RELEASES_PAGE
        out["notes"] = (data.get("body") or "")[:2000]
        out["available"] = _is_newer(tag, current)
    except Exception:
        pass   # offline / rate-limited / no release yet — stay silent
    return out


# ── Session health (real token expiry, not elapsed-time guessing) ─────────────
def _jwt_exp(token):
    """The 'exp' claim (unix seconds) of a JWT, decoded WITHOUT verification —
    we only need the expiry our own saved token claims. None if unparseable."""
    try:
        payload = token.split(".")[1]
        payload = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        exp = json.loads(payload).get("exp")
        return int(exp) if exp else None
    except Exception:
        return None


def session_health():
    """
    Inspect session.json and report the REAL credential state — by decoding the
    saved Keka access-token JWT's own expiry and the cookies' expiry stamps —
    instead of inferring anything from elapsed wall-clock time. Instant (no
    browser). Keys:

      exists          session.json is present and readable
      token_exp       unix ts when the saved access token expires (None if none found)
      token_valid     True/False for that token, or None if no token found
      remember_exp    unix ts when the 2FA remember-device cookie expires (None if absent)
      remember_valid  True/False for that cookie, or None
      alive           best static verdict: the access token's validity when known,
                      else None (unknown). A live probe (get_status) can override.
    """
    out = {"exists": False, "token_exp": None, "token_valid": None,
           "remember_exp": None, "remember_valid": None, "alive": None,
           "checked_at": int(time.time())}
    if not os.path.exists(SESSION_FILE):
        return out
    try:
        with open(SESSION_FILE, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return out
    out["exists"] = True
    now = time.time()

    # Access tokens: Keka's SPA keeps JWTs in localStorage (access_token,
    # id_token, and JWTs embedded in cached JSON blobs). Take the latest expiry.
    exps = []
    for origin in state.get("origins", []):
        for item in origin.get("localStorage", []):
            name = item.get("name") or ""
            value = item.get("value") or ""
            if name in ("access_token", "id_token"):
                e = _jwt_exp(value.strip().strip('"'))
                if e:
                    exps.append(e)
    if exps:
        out["token_exp"] = max(exps)
        out["token_valid"] = out["token_exp"] > now

    for c in state.get("cookies", []):
        if c.get("name") == "Identity.TwoFactorRememberMe":
            exp = c.get("expires") or 0
            if exp > 0:
                out["remember_exp"] = exp
                out["remember_valid"] = exp > now

    out["alive"] = out["token_valid"]
    return out


def classify_session_page(url, has_out_btn, has_in_btn):
    """Sort a probed attendance page into a session verdict:
      'in'/'out' — inside the app with the punch button visible
      'dead'     — bounced to the identity/login flow: the session truly expired
      None       — anything ambiguous (SPA still settling, maintenance page,
                   network error page). Callers must treat None as "keep the
                   previous verdict", NOT as session-dead — flashing "Session
                   expired" over a slow page load was a long-standing false alarm.
    """
    u = url or ""
    if TENANT_HOST and TENANT_HOST in u and "app.keka.com" not in u and "Account" not in u:
        if has_out_btn:
            return "in"
        if has_in_btn:
            return "out"
        return None
    if "app.keka.com" in u or "Account" in u or "login" in u.lower():
        return "dead"
    return None


def get_status():
    """Headless probe: 'in'/'out' (logged in), 'dead' (login page — session
    expired), 'ratelimited' (Keka returned HTTP 429 — back off!), or None
    (unknown/transient — see classify_session_page)."""
    if not os.path.exists(SESSION_FILE):
        return None
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=SESSION_FILE)
        page = ctx.new_page()
        # If Keka starts 429-ing us, STOP probing — hammering a rate-limited
        # portal only extends the block. Flag it so the caller backs off.
        flags = {"ratelimited": False}
        def _watch(resp):
            try:
                if resp.status == 429:
                    flags["ratelimited"] = True
            except Exception:
                pass
        page.on("response", _watch)
        try:
            page.goto(ATTENDANCE_URL, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(5000)
            if flags["ratelimited"]:
                return "ratelimited"
            return classify_session_page(
                page.url,
                page.locator('text="Web Clock-out"').count() > 0,
                page.locator('text="Web Clock-In"').count() > 0)
        finally:
            b.close()


# ── Punch action ──────────────────────────────────────────────────────────────
def click_punch(page, log, action):
    """
    Clock in/out on the attendance page. This tenant uses a TWO-STEP flow:
      1. click the "Web Clock-In" / "Web Clock-out" primary link in Actions
      2. click the red "Clock-In" / "Clock-out" confirmation button

    action: 'in' or 'out'. Returns True if the primary button was clicked.
    Playwright text matching is case-insensitive, so casing is not an issue.
    """
    if action == "in":
        primary_selectors = [
            'a:has-text("Web Clock-In")',
            'button:has-text("Web Clock-In")',
            'a:has-text("Web Check-in")',
            'a:has-text("Punch In")',
        ]
        confirm_texts = ["Clock-In", "Clock In"]
    else:
        primary_selectors = [
            'a:has-text("Web Clock-out")',
            'button:has-text("Web Clock-out")',
            'a:has-text("Web Check-out")',
            'a:has-text("Punch Out")',
        ]
        confirm_texts = ["Clock-out", "Clock Out"]

    # ── Step 1: primary button ────────────────────────────────────────────────
    clicked = False
    for sel in primary_selectors:
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                log.info("Clicked primary punch-%s: %s", action, sel)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        return False

    # ── Step 2: confirmation button (exact text so we don't re-hit "Web Clock…")
    page.wait_for_timeout(2000)
    for ct in confirm_texts:
        try:
            confirm = page.locator(f'button:text-is("{ct}"), a:text-is("{ct}")')
            if confirm.count() > 0 and confirm.first.is_visible():
                confirm.first.click()
                log.info("Clicked confirm punch-%s: %s", action, ct)
                return True
        except Exception:
            continue

    log.warning("No confirm button for punch-%s — treating primary click as final", action)
    return True


def cleanup_pngs(log):
    for f in glob.glob(tmp_path("keka_punch*.png")) + glob.glob(tmp_path("keka_captcha*.png")):
        try:
            os.remove(f)
        except Exception:
            pass
    log.info("Temp PNGs cleaned up")


def attempt_relogin(ctx, page, log):
    """
    Session expired — re-login headlessly with password + OCR captcha only.
    No OTP is needed while the TwoFactorRememberMe cookie is valid (~14 days),
    because that cookie is carried in the loaded session context.

    On success: re-saves session.json (rolling the cookies forward), lands back
    on the attendance page, and returns True. Returns False if the captcha step
    fails or the remember-device cookie has expired (OTP now required).
    """
    log.warning("Session expired — attempting auto-relogin (password + captcha, no OTP)...")
    url = submit_credentials(page, log)
    if url is None:
        log.error("Auto-relogin failed at the password/captcha step")
        return False
    if "SendCode" in url or "VerifyCode" in url:
        log.error("Remember-device cookie expired — OTP required. Re-run: python keka_setup.py")
        return False

    page.wait_for_timeout(4000)
    if not is_logged_in(page):
        log.error("Auto-relogin did not reach the app")
        return False

    save_session(ctx)
    log.info("Auto-relogin succeeded — session re-saved")
    page.goto(ATTENDANCE_URL, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(5000)
    return True


def punch_failed(action, log, msg):
    """Make a failed punch VISIBLE — feed entry + desktop notification. A
    log-file line alone means nobody notices until payroll does (this app once
    lost two days of punches that way). kind='info' on purpose: 'in'/'out'
    history kinds are read back as real punch timestamps by the UI."""
    label = "in" if action == "in" else "out"
    log.error(msg)
    log_history("info", f"Auto clock-{label} FAILED — {msg}")
    notify(f"Auto clock-{label} failed: {msg}")


# ── Main entry for the cron scripts ───────────────────────────────────────────
def run_punch(action, log_file):
    """
    Load the saved session and click punch-in/out. No login, no 2FA.
    Exits 1 (with a clear message) if session.json is missing or expired.
    """
    log = get_logger(log_file)
    label = "In" if action == "in" else "Out"
    log.info("=== Keka Punch-%s started ===", label)

    # Kill-switch and time-off gates run BEFORE anything else and are fail-open
    # (is_paused/is_timeoff swallow errors → punch proceeds), so a bad flag or a
    # corrupt timeoff.json can never wrongly BLOCK a punch — only a deliberate
    # entry does. Skips are logged as neutral history, not failures.
    today = datetime.now().strftime("%Y-%m-%d")
    if is_paused():
        log.info("Automation paused — skipping punch-%s", label)
        log_history("info", f"Auto clock-{action} skipped — automation paused")
        return
    off = is_timeoff(today)
    if off:
        why = off.get("kind", "leave")
        log.info("Time off today (%s) — skipping punch-%s", why, label)
        log_history("info", f"Auto clock-{action} skipped — {why} day")
        return

    if not EMAIL or not PASSWORD:
        punch_failed(action, log,
                     f"KEKA_EMAIL / KEKA_PASSWORD missing — set them in {ENV_FILE}")
        sys.exit(1)

    if not os.path.exists(SESSION_FILE):
        punch_failed(action, log,
                     "no saved session — open Auto-Keka and sign in")
        sys.exit(1)

    _lk = _acquire_session_lock(timeout=120, log=log)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx     = browser.new_context(storage_state=SESSION_FILE)
            page    = ctx.new_page()

            # Go straight to the attendance page using the saved session.
            # NOTE: the Keka SPA polls in the background and never reaches
            # "networkidle" — use "domcontentloaded" + a fixed settle wait instead.
            page.goto(ATTENDANCE_URL, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(5000)

            if not is_logged_in(page):
                # Try to recover automatically (password + captcha, no OTP for ~14 days)
                if not attempt_relogin(ctx, page, log):
                    shot = tmp_path(f"keka_punch{action}_expired_{datetime.now():%Y%m%d_%H%M%S}.png")
                    page.screenshot(path=shot)
                    punch_failed(action, log,
                                 "session expired and an OTP is needed — open "
                                 "Auto-Keka and press Refresh to sign in again")
                    log.error("Screenshot: %s", shot)
                    browser.close()
                    sys.exit(1)

            log.info("Session valid — attendance page loaded")

            # Idempotency guard: skip if already in the desired state.
            # Clocked-in  → primary button reads "Web Clock-out"
            # Clocked-out → primary button reads "Web Clock-In"
            already_in  = page.locator('text="Web Clock-out"').count() > 0
            already_out = page.locator('text="Web Clock-In"').count() > 0
            if action == "in" and already_in:
                log.info("Already clocked IN — nothing to do")
                log_history("in", "Already clocked in — no double-punch")
                browser.close()
                cleanup_pngs(log)
                return
            if action == "out" and already_out:
                log.info("Already clocked OUT — nothing to do")
                log_history("out", "Already clocked out — no double-punch")
                browser.close()
                cleanup_pngs(log)
                return

            if not click_punch(page, log, action):
                # SPA may still be settling (or another tab just changed state).
                # Reload, re-check idempotency, and try once more before failing.
                log.warning("Punch-%s button not found — reloading and retrying", action)
                page.goto(ATTENDANCE_URL, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(6000)
                if action == "in" and page.locator('text="Web Clock-out"').count() > 0:
                    log.info("Already clocked IN after reload — nothing to do")
                    log_history("in", "Already clocked in — no double-punch")
                    browser.close(); cleanup_pngs(log); return
                if action == "out" and page.locator('text="Web Clock-In"').count() > 0:
                    log.info("Already clocked OUT after reload — nothing to do")
                    log_history("out", "Already clocked out — no double-punch")
                    browser.close(); cleanup_pngs(log); return
                if not click_punch(page, log, action):
                    shot = tmp_path(f"keka_punch{action}_debug_{datetime.now():%Y%m%d_%H%M%S}.png")
                    page.screenshot(path=shot)
                    punch_failed(action, log,
                                 f"punch button not found on the attendance page "
                                 f"(screenshot: {shot})")
                    browser.close()
                    sys.exit(1)

            page.wait_for_timeout(3000)

            # Re-save session so its expiry keeps rolling forward
            try:
                save_session(ctx)
            except Exception:
                pass

            shot = tmp_path(f"keka_punch{action}_{datetime.now():%Y%m%d_%H%M%S}.png")
            page.screenshot(path=shot)
            log.info("Screenshot: %s", shot)
            log.info("=== Punch-%s complete ===", label)
            log_history(action, f"Clocked {'in' if action == 'in' else 'out'}")
            browser.close()
    except Exception:
        log.exception("Unhandled error during Punch-%s", label)
        punch_failed(action, log, "unexpected error — see the punch log")
        raise
    finally:
        _release_session_lock(_lk)

    cleanup_pngs(log)
