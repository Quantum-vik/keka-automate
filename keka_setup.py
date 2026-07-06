"""
Keka session setup — run this ONCE (and again only if the session expires).

    python keka_setup.py

It opens a real browser window, auto-fills your email/password/captcha, then
waits for YOU to complete the 2FA:

    1. Click "Send code to email" (or mobile) in the browser window.
    2. Enter the OTP you receive and submit.

Once you land on the Keka dashboard, the authenticated session is saved to
session.json and the cron punch scripts will reuse it — no login or OTP needed
until it expires.
"""

import sys
from datetime import datetime
from playwright.sync_api import sync_playwright

import keka_common as kc

LOG_FILE = kc.log_path("keka_setup.log")
LOGIN_WAIT_SECONDS = 300  # up to 5 minutes to finish the OTP step


def main():
    log = kc.get_logger(LOG_FILE)
    log.info("=== Keka session setup started ===")

    if not kc.EMAIL or not kc.PASSWORD:
        log.error("Missing KEKA_EMAIL / KEKA_PASSWORD — set them in %s/.env", kc.SCRIPT_DIR)
        sys.exit(1)

    with sync_playwright() as p:
        # Headful so you can complete the OTP step yourself
        browser = p.chromium.launch(headless=False, slow_mo=150)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        # ── Auto password + captcha ───────────────────────────────────────────
        url = kc.submit_credentials(page, log)
        if url is None:
            log.error("Password/captcha login failed — see the browser window.")
            page.screenshot(path=kc.tmp_path("keka_setup_fail.png"))
            browser.close()
            sys.exit(1)

        # ── Wait for the human to finish 2FA ──────────────────────────────────
        print("\n" + "=" * 68)
        print("  ACTION NEEDED — in the opened browser window:")
        print("    1. Click 'Send code to email' (or mobile)")
        print("    2. Enter the OTP you receive and submit")
        print("  Waiting up to 5 minutes for you to reach the dashboard...")
        print("=" * 68 + "\n")

        deadline = LOGIN_WAIT_SECONDS
        while deadline > 0:
            if kc.is_logged_in(page):
                break
            page.wait_for_timeout(2000)
            deadline -= 2

        if not kc.is_logged_in(page):
            log.error("Timed out waiting for 2FA. Nothing saved.")
            page.screenshot(path=kc.tmp_path("keka_setup_timeout.png"))
            browser.close()
            sys.exit(1)

        # Logged in — save the session IMMEDIATELY (it's valid now).
        log.info("Login detected — saving session")
        ctx.storage_state(path=kc.SESSION_FILE)
        log.info("Session saved to %s", kc.SESSION_FILE)

        # Best-effort: warm up the attendance page so tokens for that origin
        # are captured too. Non-fatal — the SPA never reaches networkidle.
        try:
            page.goto(kc.ATTENDANCE_URL, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(5000)
            ctx.storage_state(path=kc.SESSION_FILE)  # re-save with attendance-origin state
            log.info("Attendance page warmed up, session re-saved")
        except Exception as e:
            log.warning("Attendance warm-up skipped (%s) — session already saved", e)

        print(f"\n✅ Session saved to {kc.SESSION_FILE}")
        print("   The cron punch scripts will now run without login/OTP.\n")

        browser.close()

    log.info("=== Keka session setup complete ===")


if __name__ == "__main__":
    main()
