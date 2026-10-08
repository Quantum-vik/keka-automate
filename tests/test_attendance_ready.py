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
