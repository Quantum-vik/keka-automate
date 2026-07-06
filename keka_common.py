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
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


_env = _load_env()

# Your Keka tenant URL. Set KEKA_BASE_URL in .env (e.g. https://acme.keka.com).
BASE_URL       = os.environ.get("KEKA_BASE_URL") or _env.get("KEKA_BASE_URL", "https://<company-name>.keka.com")
TENANT_HOST    = BASE_URL.split("://")[-1].split("/")[0]   # e.g. acme.keka.com
ATTENDANCE_URL = f"{BASE_URL}/#/me/attendance/logs"

EMAIL    = os.environ.get("KEKA_EMAIL")    or _env.get("KEKA_EMAIL", "")
PASSWORD = os.environ.get("KEKA_PASSWORD") or _env.get("KEKA_PASSWORD", "")
# ─────────────────────────────────────────────────────────────────────────────


def get_logger(log_file):
    # File handler always; console handler only for interactive runs. Under
    # launchd/cron, stdout is already redirected to the log file, so adding a
    # StreamHandler there would double every line.
    handlers = [logging.FileHandler(log_file)]
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

    ctx.storage_state(path=SESSION_FILE)
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
            browser.close()
            cleanup_pngs(log)
            return
        if action == "out" and already_out:
            log.info("Already clocked OUT — nothing to do")
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
            ctx.storage_state(path=SESSION_FILE)
        except Exception:
            pass

        shot = tmp_path(f"keka_punch{action}_{datetime.now():%Y%m%d_%H%M%S}.png")
        page.screenshot(path=shot)
        log.info("Screenshot: %s", shot)
        log.info("=== Punch-%s complete ===", label)
        browser.close()

    cleanup_pngs(log)
