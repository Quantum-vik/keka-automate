"""Catching up missed punches: the same-day window for scheduled runs, the
network wait after wake, and the Linux timer installer. Offline — no browser,
no real punch, no real crontab/systemd (fakes from conftest)."""
import os
import subprocess
from datetime import datetime, timedelta

import pytest

import keka_common as kc

MON = datetime(2026, 9, 14)          # a Monday
TUE = datetime(2026, 9, 15)
SAT = datetime(2026, 9, 19)


def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return day.replace(hour=h, minute=m)


# ── the window ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("action,now,ok", [
    ("in",  at(MON, "09:00"), True),     # on time
    ("in",  at(MON, "11:40"), True),     # woke mid-morning → catch up
    ("in",  at(MON, "17:59"), True),
    ("in",  at(MON, "18:00"), False),    # workday over → never clock in now
    ("in",  at(MON, "19:30"), False),
    ("in",  at(TUE, "08:50"), False),    # yesterday's missed clock-in, fired at boot
    ("out", at(MON, "18:00"), True),     # on time
    ("out", at(MON, "23:10"), True),     # woke late evening → catch up
    ("out", at(TUE, "08:50"), False),    # never clock out yesterday's session today
    ("out", at(MON, "12:00"), False),
    ("in",  at(SAT, "10:00"), False),    # Friday's punch caught up on Saturday
    ("out", at(SAT, "19:00"), False),
])
def test_window(action, now, ok):
    assert kc.scheduled_punch_window(action, now, "09:00", "18:00")[0] is ok


def test_window_reasons_are_readable():
    _, why = kc.scheduled_punch_window("out", at(TUE, "08:50"), "09:00", "18:00")
    assert "earlier day" in why and "Keka" in why
    _, why = kc.scheduled_punch_window("in", at(MON, "19:30"), "09:00", "18:00")
    assert "18:00" in why


@pytest.mark.parametrize("in_t,out_t", [("22:00", "06:00"), ("nope", "18:00"), ("25:00", "18:00")])
def test_window_fails_open_on_odd_schedules(in_t, out_t):
    # Overnight or unparseable schedules are not second-guessed.
    assert kc.scheduled_punch_window("in", at(MON, "12:00"), in_t, out_t)[0] is True


# ── run_punch integration ─────────────────────────────────────────────────────
@pytest.fixture
def punch_env(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "PAUSE_FILE", str(tmp_path / "paused.flag"))
    monkeypatch.setattr(kc, "TIMEOFF_FILE", str(tmp_path / "timeoff.json"))
    monkeypatch.setattr(kc, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(kc, "IN_TIME", "09:00")
    monkeypatch.setattr(kc, "OUT_TIME", "18:00")
    monkeypatch.setattr(kc, "sync_playwright",
                        lambda: (_ for _ in ()).throw(AssertionError("must not launch")))
    notes = []
    monkeypatch.setattr(kc, "notify", lambda msg, *a, **k: notes.append(msg))
    # A fake clock that sleep() advances, so retries never really wait
    now = {"t": datetime.now()}
    monkeypatch.setattr(kc, "_now", lambda: now["t"])
    monkeypatch.setattr(kc.time, "sleep", lambda s: now.update(t=now["t"] + timedelta(seconds=s)))
    return {"log": str(tmp_path / "punch.log"), "notes": notes,
            "clock": lambda dt: now.update(t=dt), "now": lambda: now["t"]}


def test_scheduled_clock_in_after_workday_is_skipped(punch_env):
    punch_env["clock"](at(MON, "19:30"))
    kc.run_punch("in", punch_env["log"], scheduled=True)
    assert any("not caught up" in h["msg"] for h in kc.read_history())
    assert all(h["kind"] == "info" for h in kc.read_history())


@pytest.mark.parametrize("now", [at(TUE, "08:50"), at(SAT, "19:00")])
def test_missed_clock_out_next_morning_notifies(punch_env, now):
    punch_env["clock"](now)
    kc.run_punch("out", punch_env["log"], scheduled=True)
    assert punch_env["notes"] and "missed a clock-out" in punch_env["notes"][0]


def test_manual_punch_ignores_the_window(punch_env, monkeypatch):
    # The app's buttons run the same script without --scheduled: no window, so it
    # reaches the credential check (empty here) instead of being skipped.
    punch_env["clock"](at(MON, "19:30"))
    monkeypatch.setattr(kc, "EMAIL", "")
    with pytest.raises(SystemExit):
        kc.run_punch("in", punch_env["log"])
    assert not any("not caught up" in h["msg"] for h in kc.read_history())


def test_late_catch_up_is_noted_and_waits_for_network(punch_env, monkeypatch):
    punch_env["clock"](at(MON, "11:40"))
    waited = []
    monkeypatch.setattr(kc, "wait_for_network", lambda host, *a, **k: waited.append(host) or False)
    with pytest.raises(SystemExit):
        kc.run_punch("in", punch_env["log"], scheduled=True)
    msgs = [h["msg"] for h in kc.read_history()]
    # The note is written once; the network wait runs on every attempt
    assert sum("Catching up missed auto clock-in (was due 09:00)" in m for m in msgs) == 1
    assert waited == [kc.TENANT_HOST] * (kc.PUNCH_RETRIES + 1)
    assert any("no network" in m for m in msgs)


# ── retrying a failed scheduled punch ─────────────────────────────────────────
@pytest.fixture
def attempts(monkeypatch):
    """Stub _punch_once: results[i] is attempt i's outcome (exit code, or None
    for success); attempts past the list fail. Returns the call times."""
    calls = []

    def stub(results):
        def once(action, log, scheduled):
            calls.append(kc._now())
            r = results[len(calls) - 1] if len(calls) <= len(results) else 1
            if r is not None:
                kc.punch_failed(action, log, f"attempt {len(calls)} broke")
                raise SystemExit(r)
        monkeypatch.setattr(kc, "_punch_once", once)
        return calls
    return stub


def test_failed_scheduled_punch_is_retried_until_it_lands(punch_env, attempts):
    punch_env["clock"](at(MON, "18:00"))
    calls = attempts([1, 1, None])
    kc.run_punch("out", punch_env["log"], scheduled=True)
    assert calls == [at(MON, "18:00"), at(MON, "18:15"), at(MON, "18:30")]
    # One pop-up saying it will retry, not one per failure, and one saying it
    # worked, so the user doesn't fix by hand a punch that already happened
    assert punch_env["notes"][1:] == ["Auto clock-out succeeded on retry at 18:30"]
    assert "will retry every 15 min until 20:00" in punch_env["notes"][0]
    assert sum("FAILED" in h["msg"] for h in kc.read_history()) == 2


def test_retries_give_up_after_eight_and_keep_exit_code(punch_env, attempts):
    punch_env["clock"](at(MON, "18:00"))
    calls = attempts([])
    with pytest.raises(SystemExit) as e:
        kc.run_punch("out", punch_env["log"], scheduled=True)
    assert e.value.code == 1
    assert len(calls) == kc.PUNCH_RETRIES + 1
    assert len(punch_env["notes"]) == 2 and "gave up after 9 attempts" in punch_env["notes"][1]
    assert "attempt 9 broke" in punch_env["notes"][1]


def test_clock_in_retries_stay_clear_of_the_clock_out(punch_env, attempts):
    # A 17:50 attempt could still be running when the 18:00 clock-out starts
    punch_env["clock"](at(MON, "17:20"))
    calls = attempts([])
    with pytest.raises(SystemExit):
        kc.run_punch("in", punch_env["log"], scheduled=True)
    assert calls == [at(MON, "17:20"), at(MON, "17:35")]
    assert "gave up after 2 attempts" in punch_env["notes"][-1]


def test_retries_stop_at_the_deadline_not_just_the_count(punch_env, attempts, monkeypatch):
    punch_env["clock"](at(MON, "18:00"))
    calls = attempts([])
    once = kc._punch_once
    def slow(*a):                                   # each attempt takes 10 min
        punch_env["clock"](punch_env["now"]() + timedelta(minutes=10))
        once(*a)
    monkeypatch.setattr(kc, "_punch_once", slow)
    with pytest.raises(SystemExit):
        kc.run_punch("out", punch_env["log"], scheduled=True)
    assert len(calls) == 5                          # ends 18:10 … 19:50; 20:05 is past 20:00
    assert "gave up after 5 attempts" in punch_env["notes"][-1]


def test_unrecoverable_failure_is_not_retried(punch_env, attempts):
    punch_env["clock"](at(MON, "18:00"))
    calls = attempts([2])
    with pytest.raises(SystemExit) as e:
        kc.run_punch("out", punch_env["log"], scheduled=True)
    assert e.value.code == 2 and len(calls) == 1
    assert punch_env["notes"] == ["Auto clock-out failed: attempt 1 broke — can't be retried. "
                                  "Open Auto-Keka, sign in, and clock out from the app."]


def test_retries_stop_on_time_off(punch_env, attempts, monkeypatch):
    punch_env["clock"](at(MON, "18:00"))
    calls = attempts([])
    sleep = kc.time.sleep
    monkeypatch.setattr(kc.time, "sleep", lambda s: (sleep(s), kc.save_timeoff(
        [{"date": datetime.now().strftime("%Y-%m-%d"), "kind": "leave", "note": ""}])))
    kc.run_punch("out", punch_env["log"], scheduled=True)
    assert len(calls) == 1
    assert kc.read_history()[-1]["msg"] == "Auto clock-out retries stopped — time off today"


def test_retries_stop_once_punched_by_hand(punch_env, attempts, monkeypatch):
    punch_env["clock"](at(MON, "18:00"))
    calls = attempts([])
    sleep = kc.time.sleep
    monkeypatch.setattr(kc.time, "sleep", lambda s: (sleep(s), kc.log_history("out", "Clocked out")))
    kc.run_punch("out", punch_env["log"], scheduled=True)
    assert len(calls) == 1
    assert "by hand" in kc.read_history()[-1]["msg"]


def test_exceptions_are_retried_and_re_raised(punch_env, monkeypatch):
    punch_env["clock"](at(MON, "23:00"))
    calls = []
    monkeypatch.setattr(kc, "_punch_once",
                        lambda *a: calls.append(1) or (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        kc.run_punch("out", punch_env["log"], scheduled=True)
    assert len(calls) == 4                          # 23:00 … 23:45, then midnight closes it


def test_manual_punch_is_never_retried(punch_env, attempts):
    punch_env["clock"](at(MON, "18:00"))
    calls = attempts([])
    with pytest.raises(SystemExit):
        kc.run_punch("out", punch_env["log"])
    assert len(calls) == 1
    assert punch_env["notes"] == ["Auto clock-out failed: attempt 1 broke"]


# ── a workday left open (clock-out missed past midnight) ──────────────────────
def test_unclosed_workday():
    h = lambda d, k: {"date": d, "kind": k, "time": "09:00"}
    fri, thu = "2026-09-18", "2026-09-17"
    hist = [h(thu, "in"), h(thu, "out"), h(fri, "in"), h(fri, "info"), h("2026-09-19", "in")]
    assert kc.unclosed_workday(hist, at(TUE + timedelta(days=6), "10:00")) == fri   # Mon 21st
    assert kc.unclosed_workday(hist, at(datetime(2026, 9, 18), "20:00")) is None   # today's own day
    assert kc.unclosed_workday(hist + [h(fri, "out")], at(datetime(2026, 9, 21), "10:00")) is None
    assert kc.unclosed_workday([], at(MON, "10:00")) is None


# ── network wait ──────────────────────────────────────────────────────────────
class _Conn:
    def close(self):
        pass


def test_wait_for_network_returns_once_reachable(monkeypatch):
    tries = []

    def connect(addr, timeout):
        tries.append(addr)
        if len(tries) < 3:
            raise OSError("network unreachable")
        return _Conn()
    monkeypatch.setattr("socket.create_connection", connect)
    monkeypatch.setattr(kc.time, "sleep", lambda s: None)
    assert kc.wait_for_network("acme.keka.com", timeout=60, interval=0) is True
    assert tries[-1] == ("acme.keka.com", 443)


def test_wait_for_network_gives_up(monkeypatch):
    monkeypatch.setattr("socket.create_connection",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    monkeypatch.setattr(kc.time, "sleep", lambda s: None)
    assert kc.wait_for_network("acme.keka.com", timeout=0, interval=0) is False


# ── Linux installer (in-process; the bash wrapper is in test_install_linux) ────
def test_systemd_units_quote_awkward_paths(fake_linux_tools, monkeypatch):
    monkeypatch.setenv("FAKE_SYSTEMD", "up")
    cmd = ["/home/a b/100%/$HOME/.venv/bin/python", "/x/keka_punch_in.py", "--scheduled"]
    r = kc.install_schedule_linux(cmd, ["/x/py", "/x/keka_punch_out.py", "--scheduled"],
                                  in_time="08:05", out_time="17:45",
                                  log_file=str(fake_linux_tools["data"] / "logs" / "cron.log"))
    assert r == {"ok": True, "method": "systemd", "linger": True}
    unit = (fake_linux_tools["config"] / "systemd" / "user" / "keka-punch-in.service").read_text()
    assert 'ExecStart="/home/a b/100%%/$$HOME/.venv/bin/python" "/x/keka_punch_in.py" "--scheduled"' in unit
    assert "OnCalendar=Mon..Fri 08:05" in (
        fake_linux_tools["config"] / "systemd" / "user" / "keka-punch-in.timer").read_text()
    assert not (fake_linux_tools["config"] / "systemd" / "user" / "keka-check.timer").exists()


def test_linger_already_on_is_not_re_requested(fake_linux_tools, monkeypatch):
    monkeypatch.setenv("FAKE_SYSTEMD", "up")
    monkeypatch.setenv("FAKE_LINGER", "yes")
    r = kc.install_schedule_linux(["/x/py", "/x/keka_punch_in.py"], ["/x/py", "/x/keka_punch_out.py"])
    assert r["linger"] is True
    assert "enable-linger" not in fake_linux_tools["calls"].read_text()


def test_cron_fallback_when_forced(fake_linux_tools, monkeypatch):
    monkeypatch.setenv("FAKE_SYSTEMD", "up")
    monkeypatch.setenv("KEKA_SCHEDULER", "cron")     # wins even with systemd up
    r = kc.install_schedule_linux(["/x/py", "/x/keka_punch_in.py", "--scheduled"],
                                  ["/x/py", "/x/keka_punch_out.py", "--scheduled"],
                                  ["/x/py", "/x/keka_check.py"])
    assert r["method"] == "cron" and r["ok"]
    table = fake_linux_tools["crontab"].read_text().splitlines()
    assert table[0].startswith("0 9 * * 1-5 ")
    assert " /x/py /x/keka_punch_in.py --scheduled >> " in table[0]
    assert "XDG_RUNTIME_DIR=" in table[0]           # punches get it too, for notify-send
    assert "XDG_RUNTIME_DIR=" in table[2]           # the watchdog gets the desktop env
    assert "systemctl --user enable" not in fake_linux_tools["calls"].read_text()


def test_schedule_method_detection(fake_linux_tools, monkeypatch):
    assert kc.linux_schedule_method() is None
    fake_linux_tools["crontab"].write_text("0 9 * * 1-5 /x/py /x/keka_punch_in.py\n")
    assert kc.linux_schedule_method() == "cron"
    monkeypatch.setenv("FAKE_SYSTEMD", "up")
    kc.install_schedule_linux(["/x/py", "/x/keka_punch_in.py"], ["/x/py", "/x/keka_punch_out.py"])
    assert kc.linux_schedule_method() == "systemd"
