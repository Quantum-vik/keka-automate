"""goto_resilient(): a network wobble must not cost the whole day.

A punch caught up on wake fires while Wi-Fi is still switching interfaces.
wait_for_network() passes, then Chromium aborts the navigation already in
flight with net::ERR_NETWORK_CHANGED. Nothing retried that, so the punch
failed and the day was silently lost.
"""
import pytest
from playwright.sync_api import Error as PlaywrightError

import keka_common as kc


class FakePage:
    """Raises the queued errors in order, then succeeds."""
    def __init__(self, errors):
        self.errors = list(errors)
        self.navigations = 0

    def goto(self, url, **kw):
        self.navigations += 1
        if self.errors:
            raise self.errors.pop(0)

    def wait_for_timeout(self, ms):
        pass


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """Keep the tests instant — the backoff itself isn't under test."""
    monkeypatch.setattr(kc.time, "sleep", lambda s: None)
    monkeypatch.setattr(kc, "wait_for_network", lambda *a, **k: True)


def test_recovers_from_a_network_change():
    page = FakePage([PlaywrightError(
        "goto: net::ERR_NETWORK_CHANGED at https://x.keka.com/#/me/attendance/logs")])
    kc.goto_resilient(page, "https://x.keka.com", settle_ms=0)
    assert page.navigations == 2          # failed once, then succeeded


def test_recovers_from_a_timeout():
    page = FakePage([PlaywrightError("Timeout 30000ms exceeded.")])
    kc.goto_resilient(page, "https://x.keka.com", settle_ms=0)
    assert page.navigations == 2


def test_gives_up_after_the_last_attempt():
    errs = [PlaywrightError("goto: net::ERR_INTERNET_DISCONNECTED")] * 3
    page = FakePage(errs)
    with pytest.raises(PlaywrightError):
        kc.goto_resilient(page, "https://x.keka.com", attempts=3, settle_ms=0)
    assert page.navigations == 3


def test_non_network_errors_raise_immediately():
    """No point waiting out a bad selector or an expired session."""
    page = FakePage([PlaywrightError("Execution context was destroyed")])
    with pytest.raises(PlaywrightError):
        kc.goto_resilient(page, "https://x.keka.com", settle_ms=0)
    assert page.navigations == 1          # did NOT retry


def test_clean_load_navigates_once():
    page = FakePage([])
    kc.goto_resilient(page, "https://x.keka.com", settle_ms=0)
    assert page.navigations == 1
