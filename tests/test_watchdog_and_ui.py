"""keka_check helpers (reauth watchdog) and keka_ui pure helpers."""
import time
from datetime import datetime

import keka_check as kck
import keka_common as kc
import keka_ui
from conftest import write_session


# ── watchdog: remember-cookie expiry ─────────────────────────────────────────
def test_cookie_expiry_missing_file(session_file):
    assert kck.remember_cookie_expiry() is None


def test_cookie_expiry_corrupt_file(session_file):
    write_session(session_file, raw="}}} nope")
    assert kck.remember_cookie_expiry() is None


def test_cookie_expiry_found(session_file):
    exp = time.time() + 5 * 86400
    write_session(session_file, remember_expires=exp)
    assert kck.remember_cookie_expiry() == exp


def test_cookie_expiry_session_cookie_ignored(session_file):
    write_session(session_file, cookies=[
        {"name": "Identity.TwoFactorRememberMe", "expires": -1}])
    assert kck.remember_cookie_expiry() is None


def test_ps_str_escapes_quotes():
    assert kck._ps_str("a'b") == "'a''b'"
    assert kck._ps_str("plain") == "'plain'"


# ── UI backend: pure aggregation helpers (no Backend() instantiation — its
#    constructor starts the live status-probe thread) ─────────────────────────
def _entry(date, t, kind):
    return {"ts": 0, "time": t, "date": date, "kind": kind, "msg": ""}


def test_today_punches_first_in_last_out():
    today = datetime.now().strftime("%Y-%m-%d")
    hist = [
        _entry(today, "09:00", "in"),
        _entry(today, "09:05", "in"),      # double-punch attempt: ignored
        _entry(today, "13:00", "out"),
        _entry(today, "18:00", "out"),     # last out wins
        _entry("1999-01-01", "08:00", "in"),
    ]
    cin, cout = keka_ui.Backend._today_punches(None, hist)
    assert cin == hist[0]["ts"]
    assert cout == hist[3]["ts"]


def test_today_punches_empty():
    assert keka_ui.Backend._today_punches(None, []) == (None, None)


def test_build_week_shape():
    week = keka_ui.Backend._build_week(None, [])
    assert [d["day"] for d in week] == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    assert all(d["in"] == "—" and d["out"] == "—" for d in week)
    assert sum(1 for d in week if d["today"]) <= 1   # weekend → no 'today'


def test_build_week_places_history_on_correct_day():
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    week = keka_ui.Backend._build_week(None, [_entry(today, "09:12", "in")])
    marked = [d for d in week if d["in"] == "09:12"]
    if now.weekday() < 5:                  # weekdays: today's cell carries it
        assert len(marked) == 1 and marked[0]["today"]
    else:                                  # weekend: date not in Mon–Fri grid
        assert marked == []


# ── reauth warning (KNOWN-ISSUES #5) ─────────────────────────────────────────
def test_reauth_warning_while_clocked_in_before_out():
    due = datetime(2026, 11, 6, 20, 0)
    msg = keka_ui.reauth_warning("in", datetime(2026, 11, 6, 14, 26), due)
    assert msg == "Sign in before 20:00 or the auto clock-out may fail"


def test_reauth_warning_silent_otherwise():
    due = datetime(2026, 11, 6, 20, 0)
    assert keka_ui.reauth_warning("out", datetime(2026, 11, 6, 14, 0), due) is None
    assert keka_ui.reauth_warning(None, datetime(2026, 11, 6, 14, 0), due) is None
    assert keka_ui.reauth_warning("in", datetime(2026, 11, 6, 20, 30), due) is None
    assert keka_ui.reauth_warning("in", datetime(2026, 11, 6, 14, 0), None) is None


def test_reauth_warning_silent_on_days_without_a_clock_out(monkeypatch):
    sat = datetime(2026, 11, 7, 14, 0)
    assert keka_ui.reauth_warning("in", sat, sat.replace(hour=20)) is None
    fri = datetime(2026, 11, 6, 14, 0)
    kc.save_timeoff([{"date": "2026-11-06", "kind": "holiday", "note": ""}])
    assert keka_ui.reauth_warning("in", fri, fri.replace(hour=20)) is None
