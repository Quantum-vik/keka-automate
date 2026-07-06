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
from datetime import datetime
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
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(SCRIPT_DIR, "session.json")

# Predictable, cross-platform log dir next to the code (~/keka/logs). Same path
# on macOS/Linux/Windows, unlike tempfile.gettempdir() which varies per OS.
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
def log_path(name):
    return os.path.join(LOG_DIR, name)

# Transient screenshots go to the OS temp dir (they're auto-cleaned each run).
TMP_DIR = tempfile.gettempdir()
def tmp_path(name):
    return os.path.join(TMP_DIR, name)


def _load_env():
    """Parse ~/keka/.env (KEY=VALUE lines) into a dict. Real env vars win."""
    values = {}
    env_path = os.path.join(SCRIPT_DIR, ".env")
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
    BASE_URL = os.environ.get("KEKA_BASE_URL") or values.get("KEKA_BASE_URL", "https://<company-name>.keka.com")
    TENANT_HOST = BASE_URL.split("://")[-1].split("/")[0]
    ATTENDANCE_URL = f"{BASE_URL}/#/me/attendance/logs"
    EMAIL = os.environ.get("KEKA_EMAIL") or values.get("KEKA_EMAIL", "")
    PASSWORD = os.environ.get("KEKA_PASSWORD") or values.get("KEKA_PASSWORD", "")
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
    env_path = os.path.join(SCRIPT_DIR, ".env")
    lines = ["# Keka credentials + settings. Private — keep chmod 600."]
    lines += [f"{k}={v}" for k, v in current.items()]
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass
    reload_config()
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
    session.json holds auth cookies, so it must not be world-readable."""
    ctx.storage_state(path=SESSION_FILE)
    try:
        os.chmod(SESSION_FILE, 0o600)   # no-op-ish on Windows, harmless
    except OSError:
        pass


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
            browser.close()


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


def get_status():
    """Headless: is the user clocked 'in', 'out', or None (unknown/logged out)?"""
    if not os.path.exists(SESSION_FILE):
        return None
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=SESSION_FILE)
        page = ctx.new_page()
        try:
            page.goto(ATTENDANCE_URL, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(5000)
            if not is_logged_in(page):
                return None
            if page.locator('text="Web Clock-out"').count() > 0:
                return "in"
            if page.locator('text="Web Clock-In"').count() > 0:
                return "out"
            return None
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


# ── Main entry for the cron scripts ───────────────────────────────────────────
def run_punch(action, log_file):
    """
    Load the saved session and click punch-in/out. No login, no 2FA.
    Exits 1 (with a clear message) if session.json is missing or expired.
    """
    log = get_logger(log_file)
    label = "In" if action == "in" else "Out"
    log.info("=== Keka Punch-%s started ===", label)

    if not EMAIL or not PASSWORD:
        log.error("Missing KEKA_EMAIL / KEKA_PASSWORD — set them in %s/.env", SCRIPT_DIR)
        sys.exit(1)

    if not os.path.exists(SESSION_FILE):
        log.error("No session file at %s — run:  python keka_setup.py", SESSION_FILE)
        sys.exit(1)

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
                log.error("Could not recover session. Re-run: python keka_setup.py")
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
            shot = tmp_path(f"keka_punch{action}_debug_{datetime.now():%Y%m%d_%H%M%S}.png")
            page.screenshot(path=shot)
            log.error("Punch-%s button NOT found. Screenshot: %s", action, shot)
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

    cleanup_pngs(log)
