"""wait_for_attendance_ready(): never read a page that hasn't rendered.

The URL is already /me/attendance/logs while Keka is still showing its loading
splash, so is_logged_in() passes. The old code slept a flat 5s, logged "Session
valid — attendance page loaded" and read the punch buttons off a logo. On a slow
load (after a network retry) it found nothing, gave up, and left the day open.
"""
import logging
import os

import pytest
from playwright.sync_api import Error as PlaywrightError

import keka_common as kc


class FakeLocator:
    def __init__(self, appears):
        self._appears = appears
        self.waits = 0

    def or_(self, other):
        return self

    @property
    def first(self):
        return self

    def wait_for(self, state=None, timeout=None):
        self.waits += 1
        if not self._appears:
            raise PlaywrightError(f"Timeout {timeout}ms exceeded.")

    def count(self):
        return 0


class FakePage:
    def __init__(self, appears):
        self.locator_obj = FakeLocator(appears)

    def locator(self, sel):
        return self.locator_obj


def test_true_when_a_punch_button_renders():
    assert kc.wait_for_attendance_ready(FakePage(True)) is True


def test_false_when_the_page_never_renders():
    """The splash-screen case — must report failure, not pretend it loaded."""
    assert kc.wait_for_attendance_ready(FakePage(False)) is False


def test_punch_path_waits_generously(monkeypatch):
    page = FakePage(True)
    captured = {}
    orig = page.locator_obj.wait_for

    def spy(state=None, timeout=None):
        captured["timeout"] = timeout
        return orig(state=state, timeout=timeout)
    page.locator_obj.wait_for = spy

    kc.wait_for_attendance_ready(page)
    # A fixed 5s sleep is what caused the miss. A punch that lands late still
    # lands; a missed one costs a day, so this default must outlast a slow SPA.
    assert captured["timeout"] >= 120_000


def test_callers_can_shorten_the_wait():
    """The 15-minute status probe gives up early rather than blocking."""
    page = FakePage(False)
    captured = {}
    page.locator_obj.wait_for = lambda state=None, timeout=None: (
        captured.update(timeout=timeout), (_ for _ in ()).throw(
            PlaywrightError("Timeout")))[1]
    assert kc.wait_for_attendance_ready(page, timeout=30_000) is False
    assert captured["timeout"] == 30_000


def test_failure_is_logged(caplog):
    class Log:
        def __init__(self): self.warnings = []
        def warning(self, msg, *a): self.warnings.append(msg % a if a else msg)
    log = Log()
    kc.wait_for_attendance_ready(FakePage(False), log)
    assert log.warnings and "rendered" in log.warnings[0]


# ── run_punch: a login page under the attendance URL (2026-11-06) ────────────
class PunchPage:
    """Attendance URL throughout, like Keka's SPA before its auth redirect.
    Shows the login form until logged in, then the `shows` punch button.
    `stuck` makes every wait time out (a punch click that never lands)."""
    url = f"https://{kc.TENANT_HOST or 'acme.keka.com'}/#/me/attendance/logs"

    def __init__(self):
        self.logged_in = False
        self.shows = kc.PUNCH_TEXT["out"]          # clocked in
        self.stuck = False

    def locator(self, sel):
        page = self

        class L:
            first = property(lambda s: s)
            def or_(s, other): return s
            def wait_for(s, **k):
                if page.stuck:
                    raise PlaywrightError("Timeout 30000ms exceeded.")
            def count(s):
                if sel == kc.LOGIN_BUTTON:
                    return 0 if page.logged_in else 1
                return 1 if page.logged_in and page.shows in sel else 0
        return L()

    def wait_for_timeout(self, ms): pass
    def screenshot(self, path): pass
    def on(self, event, cb): pass


@pytest.fixture
def punch(tmp_path, monkeypatch):
    """run_punch against PunchPage with every side effect faked. The session
    lock times out (None) unless a test swaps _acquire_session_lock."""
    page = PunchPage()
    session = tmp_path / "session.json"
    session.write_text("{}")
    for name, val in {
        "SESSION_FILE": str(session), "HISTORY_FILE": str(tmp_path / "h.jsonl"),
        "PAUSE_FILE": str(tmp_path / "p"), "TIMEOFF_FILE": str(tmp_path / "t.json"),
        "TMP_DIR": str(tmp_path), "EMAIL": "e", "PASSWORD": "p",
        "log_step": lambda *a, **k: None, "notify": lambda *a, **k: None,
        "_acquire_session_lock": lambda **k: None,
        "_release_session_lock": lambda f: None,
        "goto_resilient": lambda *a, **k: True,
    }.items():
        monkeypatch.setattr(kc, name, val)
    t = type("Punch", (), {})()
    t.page, t.relogins, t.clicks, t.saves = page, [], [], []
    monkeypatch.setattr(kc, "save_session", lambda ctx: t.saves.append(ctx))
    monkeypatch.setattr(kc, "attempt_relogin",
                        lambda ctx, pg, log: t.relogins.append(1) or setattr(pg, "logged_in", True) or True)
    def click(pg, log, action):                  # a punch that lands flips the button
        t.clicks.append(pg.logged_in)
        pg.shows = kc.PUNCH_TEXT["out" if action == "in" else "in"]
        return True
    monkeypatch.setattr(kc, "click_punch", click)

    class Browser:
        def new_context(self, **k):
            return type("Ctx", (), {"new_page": lambda s: page})()
        def close(self): pass

    class PW:
        chromium = type("C", (), {"launch": lambda s, **k: Browser()})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(kc, "sync_playwright", lambda: PW())
    t.run = lambda action: kc.run_punch(action, str(tmp_path / "punch.log"))
    t.history = lambda: [(h["kind"], h["msg"]) for h in kc.read_history()]
    return t


def test_punch_relogs_when_login_page_hides_under_attendance_url(punch):
    # Logged out → Clock-out button absent and login form present: must relog,
    # then punch. Before the fix it read the URL, called it "Session valid",
    # never relogged, and exited 1 with "punch button not found".
    punch.run("out")
    assert punch.relogins == [1]
    assert punch.clicks == [True]
    assert [k for k, _ in punch.history()] == ["out"]


def test_skipped_punch_is_not_history_as_a_real_punch(punch):
    # Already clocked out: "out" history would be read back as a clock-out time.
    punch.page.logged_in = True
    punch.page.shows = kc.PUNCH_TEXT["in"]
    punch.run("out")
    assert punch.clicks == []
    assert punch.history() == [("info", "Already clocked out — no double-punch")]


def test_no_stale_session_save_when_the_lock_timed_out(punch, monkeypatch):
    punch.page.logged_in = True
    punch.run("out")
    assert [k for k, _ in punch.history()] == ["out"]
    assert punch.saves == []
    # Holding the lock, the write-back still happens.
    monkeypatch.setattr(kc, "_acquire_session_lock", lambda **k: object())
    punch.run("in")
    assert len(punch.saves) == 1


def test_interactive_login_skips_stale_save_without_lock(punch, monkeypatch):
    punch.page.logged_in = True
    assert kc.interactive_login(lambda **k: None, logging.getLogger("t")) is True
    assert punch.saves == []
    monkeypatch.setattr(kc, "_acquire_session_lock", lambda **k: object())
    assert kc.interactive_login(lambda **k: None, logging.getLogger("t")) is True
    assert len(punch.saves) == 1


def test_click_that_never_lands_is_a_failure_not_a_punch(punch, monkeypatch):
    # click_punch returns True after a primary click with no confirm dialog;
    # the other button never shows up, so the punch did not take.
    punch.page.logged_in = True
    monkeypatch.setattr(kc, "click_punch",
                        lambda pg, log, action: setattr(pg, "stuck", True) or True)
    with pytest.raises(SystemExit) as e:
        punch.run("out")
    assert e.value.code == 1
    kinds = [k for k, _ in punch.history()]
    assert "out" not in kinds and kinds == ["info"]
    assert "never appeared" in punch.history()[0][1]


def test_failed_relogin_message_does_not_guess_otp(punch, monkeypatch):
    monkeypatch.setattr(kc, "attempt_relogin", lambda ctx, pg, log: False)
    with pytest.raises(SystemExit):
        punch.run("out")
    (kind, msg), = punch.history()
    assert kind == "info" and "automatic sign-in failed" in msg and "OTP" not in msg


def test_missing_tesseract_is_named(punch, monkeypatch):
    def no_tesseract(ctx, pg, log):
        raise kc.pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(kc, "attempt_relogin", no_tesseract)
    with pytest.raises(SystemExit) as e:
        punch.run("out")
    assert e.value.code == 2                         # retrying can't install it
    (kind, msg), = punch.history()
    assert kind == "info" and "tesseract" in msg


def test_get_status_dead_when_login_form_under_tenant_url(punch, monkeypatch):
    # Logged out, tenant URL, login button drawn: "dead", not None.
    assert kc.get_status() == "dead"
    punch.page.logged_in = True
    assert kc.get_status() == "in"


def test_punch_confirmed_only_after_reload_is_recorded(punch, monkeypatch):
    # The click landed but the button swap showed up late: a reload shows it.
    # Failing here made the retry log "Already clocked out" and lose the punch.
    punch.page.logged_in = True
    def click(pg, log, action):
        pg.shows, pg.stuck = kc.PUNCH_TEXT["in"], True
        return True
    monkeypatch.setattr(kc, "click_punch", click)
    punch.run("out")
    assert [k for k, _ in punch.history()] == ["out"]


def test_punch_is_recorded_before_the_screenshot(punch, monkeypatch):
    punch.page.logged_in = True
    monkeypatch.setattr(PunchPage, "screenshot",
                        lambda s, path: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        punch.run("out")
    assert [k for k, _ in punch.history()][0] == "out"


def test_otp_required_exits_2_and_missing_session_too(punch, monkeypatch):
    def otp(ctx, pg, log):
        pg.url = "https://app.keka.com/Account/SendCode"
        return False
    monkeypatch.setattr(kc, "attempt_relogin", otp)
    with pytest.raises(SystemExit) as e:
        punch.run("out")
    assert e.value.code == 2 and "OTP" in punch.history()[-1][1]
    os.remove(kc.SESSION_FILE)
    with pytest.raises(SystemExit) as e:
        punch.run("out")
    assert e.value.code == 2
