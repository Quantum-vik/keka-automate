"""wait_for_attendance_ready(): never read a page that hasn't rendered.

The URL is already /me/attendance/logs while Keka is still showing its loading
splash, so is_logged_in() passes. The old code slept a flat 5s, logged "Session
valid — attendance page loaded" and read the punch buttons off a logo. On a slow
load (after a network retry) it found nothing, gave up, and left the day open.
"""
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
    Shows the login form until relogged in, then the clock-out button."""
    url = f"https://{kc.TENANT_HOST or 'acme.keka.com'}/#/me/attendance/logs"

    def __init__(self):
        self.logged_in = False

    def locator(self, sel):
        page = self

        class L:
            first = property(lambda s: s)
            def or_(s, other): return s
            def wait_for(s, **k): pass        # something always renders
            def count(s):
                if sel == kc.LOGIN_BUTTON:
                    return 0 if page.logged_in else 1
                return 1 if page.logged_in and "Clock-out" in sel else 0
        return L()

    def wait_for_timeout(self, ms): pass
    def screenshot(self, path): pass


def test_punch_relogs_when_login_page_hides_under_attendance_url(tmp_path, monkeypatch):
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
        "goto_resilient": lambda *a, **k: True, "save_session": lambda ctx: None,
    }.items():
        monkeypatch.setattr(kc, name, val)
    relogins, clicks = [], []
    monkeypatch.setattr(kc, "attempt_relogin",
                        lambda ctx, pg, log: relogins.append(1) or setattr(pg, "logged_in", True) or True)
    monkeypatch.setattr(kc, "click_punch",
                        lambda pg, log, action: clicks.append(pg.logged_in) or True)

    class Browser:
        def new_context(self, **k):
            return type("Ctx", (), {"new_page": lambda s: page})()
        def close(self): pass

    class PW:
        chromium = type("C", (), {"launch": lambda s, **k: Browser()})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(kc, "sync_playwright", lambda: PW())

    # Logged out → Clock-out button absent and login form present: must relog,
    # then punch. Before the fix it read the URL, called it "Session valid",
    # never relogged, and exited 1 with "punch button not found".
    kc.run_punch("out", str(tmp_path / "punch.log"))
    assert relogins == [1]
    assert clicks == [True]
    assert [h["kind"] for h in kc.read_history()] == ["out"]
