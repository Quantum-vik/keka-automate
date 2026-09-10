"""Token-refresh hardening: page classification, OTP timeout, the
cross-process session lock, and punch-failure visibility."""
import logging
import threading
import time
from types import SimpleNamespace

import keka_common as kc
import keka_ui


# ── classify_session_page: the get_status verdict, minus the browser ─────────
def _cls(url, has_out=False, has_in=False, host="acme.keka.com", monkeypatch=None):
    monkeypatch.setattr(kc, "TENANT_HOST", host)
    return kc.classify_session_page(url, has_out, has_in)


def test_classify_clocked_in(monkeypatch):
    assert _cls("https://acme.keka.com/#/me/attendance", has_out=True,
                monkeypatch=monkeypatch) == "in"


def test_classify_clocked_out(monkeypatch):
    assert _cls("https://acme.keka.com/#/me/attendance", has_in=True,
                monkeypatch=monkeypatch) == "out"


def test_classify_login_bounce_is_dead(monkeypatch):
    # Redirected to the identity flow → the session definitively expired.
    assert _cls("https://app.keka.com/Account/Login",
                monkeypatch=monkeypatch) == "dead"


def test_classify_settling_spa_is_unknown(monkeypatch):
    # Inside the app but neither punch button rendered yet — NOT dead.
    # (This exact case used to flash "Session expired" over a slow load.)
    assert _cls("https://acme.keka.com/#/me/attendance",
                monkeypatch=monkeypatch) is None


def test_classify_error_page_is_unknown(monkeypatch):
    assert _cls("chrome-error://chromewebdata/", monkeypatch=monkeypatch) is None
    assert _cls("", monkeypatch=monkeypatch) is None


# ── OTP prompt timeout: an abandoned prompt must not block forever ───────────
def _otp_stub(emitted, logged):
    return SimpleNamespace(
        emit=lambda obj: emitted.append(obj),
        push_log=lambda msg, kind="info": logged.append(msg),
        _otp_event=threading.Event(),
        _otp_value=None,
    )


def test_otp_timeout_returns_none_and_retracts_prompt(monkeypatch):
    monkeypatch.setattr(keka_ui, "OTP_WAIT_SECS", 0.15)
    emitted, logged = [], []
    stub = _otp_stub(emitted, logged)
    assert keka_ui.Backend._otp_getter(stub, retry=False) is None
    types = [e.get("type") for e in emitted]
    assert types == ["otp", "otpDone"]     # prompt shown, then retracted
    assert logged                          # the cancellation is visible in the feed


def test_otp_submitted_in_time(monkeypatch):
    monkeypatch.setattr(keka_ui, "OTP_WAIT_SECS", 5)
    emitted, logged = [], []
    stub = _otp_stub(emitted, logged)

    def submit():
        time.sleep(0.05)
        stub._otp_value = "123456"
        stub._otp_event.set()

    threading.Thread(target=submit).start()
    assert keka_ui.Backend._otp_getter(stub, retry=False) == "123456"
    assert [e.get("type") for e in emitted] == ["otp"]   # no spurious otpDone


# ── cross-process session lock ───────────────────────────────────────────────
def test_session_lock_exclusive_and_reacquirable(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "SESSION_LOCK_FILE", str(tmp_path / "session.lock"))
    first = kc._acquire_session_lock(timeout=5)
    assert first is not None
    # Contended: a second acquisition (fresh fd, same file) must time out fast
    # and yield None — callers proceed unlocked rather than skip a punch.
    assert kc._acquire_session_lock(timeout=0) is None
    kc._release_session_lock(first)
    second = kc._acquire_session_lock(timeout=5)
    assert second is not None
    kc._release_session_lock(second)


def test_session_lock_release_none_is_noop():
    kc._release_session_lock(None)   # must not raise


# ── punch failures must be visible, and must NOT read back as punches ────────
def test_punch_failed_writes_feed_and_notifies(history_file, monkeypatch):
    calls = []
    monkeypatch.setattr(kc, "notify", lambda msg, title="": calls.append(msg))
    log = logging.getLogger("test_punch_failed")
    log.addHandler(logging.NullHandler())

    kc.punch_failed("out", log, "session expired and an OTP is needed")

    assert calls and "clock-out failed" in calls[0]
    hist = kc.read_history()
    assert len(hist) == 1
    entry = hist[0]
    assert "FAILED" in entry["msg"]
    # Regression guard: 'in'/'out' kinds are read back as real punch times by
    # _today_punches/_build_week — a failure entry must never masquerade as one.
    assert entry["kind"] == "info"
    cin, cout = keka_ui.Backend._today_punches(None, hist)
    assert (cin, cout) == (None, None)
