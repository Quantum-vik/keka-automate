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


def _fail_entry():
    return {"kind": "info", "msg": "Auto clock-out FAILED — punch button not found"}


def test_last_punch_failure_lone_failure_is_returned():
    hist = [{"kind": "in", "msg": "Clocked in"}, _fail_entry(),
            {"kind": "info", "msg": "Session refreshed"}]
    assert kc.last_punch_failure(hist) is hist[1]


def test_last_punch_failure_cleared_by_later_punch():
    assert kc.last_punch_failure([_fail_entry(), {"kind": "out", "msg": "Clocked out"}]) is None
    assert kc.last_punch_failure([]) is None


def test_last_punch_failure_only_cleared_by_the_same_action():
    hist = [_fail_entry(), {"kind": "in", "msg": "Clocked in"}]
    assert kc.last_punch_failure(hist) is hist[0]     # today's clock-in ≠ yesterday's clock-out


def test_last_punch_failure_counts_a_missed_clock_out():
    hist = [{"kind": "info", "msg": "Missed auto clock-out not caught up — it's the weekend"}]
    assert kc.last_punch_failure(hist) is hist[0]
    assert kc.last_punch_failure(hist + [{"kind": "out", "msg": "Clocked out"}]) is None


def test_last_punch_failure_hidden_once_dismissed():
    hist = [dict(_fail_entry(), ts=100)]
    assert kc.last_punch_failure(hist, 100) is None
    assert kc.last_punch_failure(hist, 99) is hist[0]
    newer = [dict(_fail_entry(), ts=101)]
    assert kc.last_punch_failure(newer, 100) is newer[0]
    assert kc.last_punch_failure(hist, 0) is hist[0]
    no_ts = [_fail_entry()]                            # fixtures without ts still return
    assert kc.last_punch_failure(no_ts) is no_ts[0]


def test_dismiss_failure_round_trip_keeps_the_max():
    assert kc.dismissed_failure_ts() == 0
    kc.dismiss_failure(200)
    assert kc.dismissed_failure_ts() == 200
    kc.dismiss_failure(150)                            # a stale page can't un-dismiss
    assert kc.dismissed_failure_ts() == 200


def test_dismissed_failure_ts_corrupt_or_partial_file_is_zero():
    p = kc.os.path.join(kc.DATA_DIR, "failure_dismissed")
    for junk in ("not a number", "", "1.7e"):                # garbage, empty, a half-written value
        with open(p, "w") as f:
            f.write(junk)
        assert kc.dismissed_failure_ts() == 0
    kc.dismiss_failure(300)                                  # a corrupt file is overwritten cleanly
    assert kc.dismissed_failure_ts() == 300
    assert not kc.os.path.exists(p + ".tmp")
