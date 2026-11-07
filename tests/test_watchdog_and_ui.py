"""keka_check helpers (reauth watchdog) and keka_ui pure helpers."""
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

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
    assert [d["iso"][-2:].lstrip("0") for d in week] == [d["date"].split("/")[1] for d in week]
    assert all(len(d["iso"]) == 10 and d["iso"][4] == "-" for d in week)   # YYYY-MM-DD
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


# Thu 11-05 in/out, Fri 11-06 in only (auto clock-out failed)
_MISSED_FRI = [_entry("2026-11-05", "11:00", "in"), _entry("2026-11-05", "20:00", "out"),
               _entry("2026-11-06", "11:00", "in")]


def test_build_week_flags_past_day_without_clock_out():
    week = keka_ui.Backend._build_week(None, _MISSED_FRI, now=datetime(2026, 11, 7, 23, 0))
    by = {d["day"]: d for d in week}
    assert by["Fri"]["open"] and by["Fri"]["in"] == "11:00" and by["Fri"]["out"] == "—"
    assert not by["Thu"]["open"]
    assert not any(d["open"] for d in week if d["day"] not in ("Fri",))   # empty days aren't open


def test_build_week_never_flags_today_in_progress():
    week = keka_ui.Backend._build_week(None, _MISSED_FRI, now=datetime(2026, 11, 6, 15, 0))
    fri = week[4]
    assert fri["today"] and fri["in"] == "11:00" and not fri["open"]


def test_build_week_flags_in_out_in_and_out_before_in():
    hist = [_entry("2026-11-04", "09:00", "in"), _entry("2026-11-04", "13:00", "out"),
            _entry("2026-11-04", "14:00", "in"),                       # never clocked out again
            _entry("2026-11-05", "11:00", "in"), _entry("2026-11-05", "11:00", "out")]   # out <= in
    week = keka_ui.Backend._build_week(None, hist, now=datetime(2026, 11, 7, 23, 0))
    assert week[2]["open"] and week[3]["open"]


def _state_with(monkeypatch, hist, status):
    """Run the real get_state on a Backend built without __init__ (that starts
    the probe threads); only the instance state get_state reads is set."""
    monkeypatch.setattr(kc, "read_history", lambda n=200: hist)
    monkeypatch.setattr(kc, "session_health", lambda: {
        "remember_exp": None, "alive": None, "token_exp": None, "identity_exp": None})
    monkeypatch.setattr(kc, "deps_ready", lambda: True)
    monkeypatch.setattr(keka_ui.lic, "license_info", lambda: None)
    monkeypatch.setattr(keka_ui.lic, "machine_id", lambda: "x")
    me = keka_ui.Backend.__new__(keka_ui.Backend)
    me._status, me._alive, me._update = status, None, None
    me._rate_limited = me._needs_reauth = False
    return me.get_state()


def _last_weekday(now, back=1):
    d = now - timedelta(days=back)
    while d.weekday() > 4:
        d -= timedelta(days=1)
    return d


def test_get_state_names_unclosed_day(monkeypatch):
    day = _last_weekday(datetime.now()).strftime("%Y-%m-%d")
    st = _state_with(monkeypatch, [_entry(day, "11:00", "in")], "in")
    assert st["unclosedDay"] == day
    assert st["clockedIn"] and st["clockInAt"] is None


def test_get_state_manual_clock_in_is_not_unclosed(monkeypatch):
    # clocked in from Keka's own app: our run logs only an info line, no "in"
    today = datetime.now().strftime("%Y-%m-%d")
    st = _state_with(monkeypatch, [_entry(today, "11:00", "info")], "in")
    assert st["clockedIn"] and st["clockInAt"] is None and st["unclosedDay"] is None


def test_recent_unclosed_day_caps_at_three_days():
    hist = [_entry("2026-11-06", "11:00", "in")]                       # Friday
    assert keka_ui.recent_unclosed_day(hist, datetime(2026, 11, 9, 23, 0)) == "2026-11-06"   # Mon
    assert keka_ui.recent_unclosed_day(hist, datetime(2026, 11, 10, 9, 0)) is None          # Tue


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


# ── failure banner dismissal ─────────────────────────────────────────────────
def _fail(ts):
    return {"ts": ts, "time": "20:04", "date": "2026-11-06", "kind": "info",
            "msg": "Auto clock-out FAILED — punch button not found"}


def test_get_state_hides_dismissed_failure_until_a_newer_one(monkeypatch):
    assert _state_with(monkeypatch, [_fail(100)], "out")["lastFailure"]["ts"] == 100
    kc.dismiss_failure(100)
    assert _state_with(monkeypatch, [_fail(100)], "out")["lastFailure"] is None
    assert _state_with(monkeypatch, [_fail(100), _fail(101)], "out")["lastFailure"]["ts"] == 101


def test_dismiss_failure_only_accepts_the_current_failure(monkeypatch):
    now_ms = int(time.time() * 1000)
    monkeypatch.setattr(kc, "read_history", lambda n=200: [_fail(now_ms)])
    me = keka_ui.Backend.__new__(keka_ui.Backend)
    me.push_state = lambda: None
    for obj in (None, {}, {"ts": 0}, {"ts": -5}, {"ts": "x"}, {"ts": True},
                {"ts": now_ms + 86400_000}, {"ts": float("inf")}, {"ts": 10**18},
                {"ts": now_ms - 1}):                       # not the failure on screen
        assert me.dismiss_failure(obj) == {"ok": False, "message": "Nothing to dismiss"}, obj
    assert not kc.os.path.exists(kc.os.path.join(kc.DATA_DIR, "failure_dismissed"))
    assert me.dismiss_failure({"ts": now_ms}) == {"ok": True}
    assert kc.dismissed_failure_ts() == now_ms
    assert me.dismiss_failure({"ts": now_ms}) == {"ok": True}    # idempotent: desk + phone both dismiss


def test_dismiss_failure_with_no_failure_writes_nothing(monkeypatch):
    monkeypatch.setattr(kc, "read_history", lambda n=200: [])
    me = keka_ui.Backend.__new__(keka_ui.Backend)
    me.push_state = lambda: None
    assert me.dismiss_failure({"ts": 1})["ok"] is False
    assert kc.dismissed_failure_ts() == 0


def test_dismiss_failure_is_wired_into_http_and_shim():
    import inspect
    assert "dismiss_failure:(o)=>post('/api/dismiss_failure',o)" in keka_ui._SHIM
    assert '"/api/dismiss_failure": lambda: backend.dismiss_failure(body)' in inspect.getsource(keka_ui._serve_http)
    assert keka_ui.Api.dismiss_failure


# ── apply_schedule: payload keys and validation ─────────────────────────────
def _schedule(monkeypatch, obj):
    calls = []
    monkeypatch.setattr(kc, "FROZEN", True)
    monkeypatch.setattr(kc, "install_schedule_native", lambda i, o: calls.append((i, o)) or True)
    monkeypatch.setattr(kc, "linger_warning", lambda: None)
    me = keka_ui.Backend.__new__(keka_ui.Backend)
    me.push_state = lambda: None
    return me.apply_schedule(obj), calls


def test_apply_schedule_accepts_legacy_in_out(monkeypatch):
    res, calls = _schedule(monkeypatch, {"in": "10:00", "out": "19:00"})
    env = kc._load_env()
    assert res["ok"] and calls == [("10:00", "19:00")]
    assert env["KEKA_IN_TIME"] == "10:00" and env["KEKA_OUT_TIME"] == "19:00"


def test_apply_schedule_accepts_in_time_out_time(monkeypatch):
    res, calls = _schedule(monkeypatch, {"inTime": "08:30", "outTime": "17:30"})
    assert res["ok"] and calls == [("08:30", "17:30")]
    assert kc._load_env()["KEKA_IN_TIME"] == "08:30"


def test_apply_schedule_accepts_short_hour_and_padding(monkeypatch):
    res, calls = _schedule(monkeypatch, {"inTime": "9:00", "outTime": " 18:00 "})
    assert res["ok"] and calls == [("9:00", "18:00")]


def test_apply_schedule_rejects_missing_or_bad_times(monkeypatch):
    for obj in ({}, {"inTime": "25:99", "outTime": "18:00"}, {"inTime": "24:00", "outTime": "18:00"},
                {"inTime": 900, "outTime": 1800},                       # numbers: no AttributeError
                {"inTime": "\u0660\u0669:\u0660\u0660", "outTime": "18:00"}):   # Arabic-Indic 09:00
        res, calls = _schedule(monkeypatch, obj)
        assert res == {"ok": False, "message": "Use 24-hour HH:MM, e.g. 09:00 and 18:00."}
        assert calls == []
        assert not kc.os.path.exists(kc.ENV_FILE)
