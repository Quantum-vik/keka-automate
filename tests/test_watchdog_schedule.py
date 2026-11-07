"""The compiled app must schedule the reauth watchdog (--check) next to the
punches on every OS — it once installed only the punches, so the device pass
lapsed with no warning — and repair older installs that are missing it."""

import logging

import keka_common as kc
import keka_check


def test_linux_native_schedule_includes_watchdog(fake_linux_tools, monkeypatch):
    monkeypatch.setattr(kc, "APP_EXECUTABLE", "/opt/Auto-Keka")
    monkeypatch.setattr(kc.sys, "platform", "linux")
    assert kc.install_schedule_native("09:00", "18:00") is True
    assert "/opt/Auto-Keka --check >> " in fake_linux_tools["crontab"].read_text()
    assert kc.schedule_status() == {"punch": True, "watchdog": True}


def test_linux_systemd_native_schedule_includes_watchdog(fake_linux_tools, monkeypatch):
    monkeypatch.setenv("FAKE_SYSTEMD", "up")
    monkeypatch.setattr(kc, "APP_EXECUTABLE", "/opt/Auto-Keka")
    monkeypatch.setattr(kc.sys, "platform", "linux")
    assert kc.install_schedule_native("09:00", "18:00") is True
    unit = fake_linux_tools["config"] / "systemd" / "user" / "keka-check.service"
    assert 'ExecStart="/opt/Auto-Keka" "--check"' in unit.read_text()


def test_cron_reapply_replaces_old_watchdog_line(fake_linux_tools, monkeypatch):
    monkeypatch.setattr(kc, "APP_EXECUTABLE", "/opt/Auto-Keka")
    monkeypatch.setattr(kc.sys, "platform", "linux")
    kc.install_schedule_native("09:00", "18:00")
    kc.install_schedule_native("10:00", "19:00")
    assert fake_linux_tools["crontab"].read_text().count("--check") == 1


def test_windows_native_schedule_includes_watchdog(monkeypatch):
    calls = []
    monkeypatch.setattr(kc, "APP_EXECUTABLE", r"C:\Apps\Auto-Keka.exe")
    monkeypatch.setattr(kc.sys, "platform", "win32")
    monkeypatch.setattr(kc.subprocess, "run",
                        lambda cmd, **k: calls.append(cmd) or kc.subprocess.CompletedProcess(cmd, 0))
    assert kc.install_schedule_native("09:00", "18:00") is True
    tasks = {c[c.index("/TN") + 1]: c for c in calls}
    assert tasks[r"Keka\Reauth"][tasks[r"Keka\Reauth"].index("/TR") + 1] == \
        r'"C:\Apps\Auto-Keka.exe" --check'
    assert "6" in tasks[r"Keka\Reauth"] and "ONLOGON" in tasks[r"Keka\ReauthLogon"]


def test_windows_refused_logon_trigger_still_ok(monkeypatch):
    monkeypatch.setattr(kc.sys, "platform", "win32")
    monkeypatch.setattr(kc.subprocess, "run", lambda cmd, **k: kc.subprocess.CompletedProcess(
        cmd, 1 if "ONLOGON" in cmd else 0))
    assert kc.install_schedule_native("09:00", "18:00") is True


def test_macos_native_schedule_includes_watchdog(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "APP_EXECUTABLE", "/Applications/Auto-Keka.app/Contents/MacOS/Auto-Keka")
    monkeypatch.setattr(kc.sys, "platform", "darwin")
    monkeypatch.setattr(kc.os, "getuid", lambda: 501, raising=False)   # absent on Windows
    monkeypatch.setattr(kc.os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    monkeypatch.setattr(kc.subprocess, "run", lambda cmd, **k: kc.subprocess.CompletedProcess(cmd, 0))
    assert kc.install_schedule_native("09:00", "18:00") is True
    la = tmp_path / "Library" / "LaunchAgents"
    reauth = (la / "com.keka.reauth.plist").read_text()
    assert "<string>--check</string>" in reauth and "<integer>21600</integer>" in reauth
    assert "RunAtLoad" in reauth
    assert "<string>--punch</string><string>in</string>" in (la / "com.keka.punchin.plist").read_text()
    assert kc.schedule_status() == {"punch": True, "watchdog": True}


def test_startup_repair_only_when_watchdog_missing(monkeypatch):
    installed = []
    monkeypatch.setattr(kc, "FROZEN", True)
    monkeypatch.setattr(kc, "install_schedule_native", lambda i, o: installed.append((i, o)) or True)
    for status, expect in (({"punch": True, "watchdog": False}, 1),
                           ({"punch": True, "watchdog": True}, 0),
                           ({"punch": False, "watchdog": False}, 0),   # never scheduled
                           ({"punch": True, "watchdog": None}, 0)):    # can't tell
        installed.clear()
        monkeypatch.setattr(kc, "schedule_status", lambda s=status: s)
        kc.ensure_watchdog_schedule()
        assert len(installed) == expect, status


def test_startup_repair_skips_source_runs(monkeypatch):
    monkeypatch.setattr(kc, "FROZEN", False)
    monkeypatch.setattr(kc, "schedule_status", lambda: {"punch": True, "watchdog": False})
    assert kc.ensure_watchdog_schedule() is False


def test_frozen_watchdog_opens_the_app_not_keka_setup(monkeypatch):
    opened = []
    monkeypatch.setattr(kc, "FROZEN", True)
    monkeypatch.setattr(kc, "APP_EXECUTABLE", "/opt/Auto-Keka")
    monkeypatch.setattr(keka_check, "_has_display", lambda: True)
    monkeypatch.setattr(keka_check, "notify", lambda m: None)
    monkeypatch.setattr(keka_check, "confirm_dialog", lambda m: True)
    monkeypatch.setattr(keka_check.subprocess, "Popen", lambda cmd: opened.append(cmd))
    monkeypatch.setattr(keka_check.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran keka_setup")))
    keka_check.launch_setup(logging.getLogger("test"))
    assert opened == [["/opt/Auto-Keka"]]


def test_watchdog_reminds_about_a_missed_clock_out_for_three_days(monkeypatch):
    from datetime import datetime
    notes = []
    monkeypatch.setattr(keka_check, "notify", notes.append)
    monkeypatch.setattr(keka_check, "launch_setup", lambda log: None)
    kc.log_history("info", "unrelated")
    with open(kc.HISTORY_FILE, "a") as f:
        f.write('{"date": "2026-09-18", "time": "09:00", "kind": "in", "msg": "Clocked in"}\n')
    for now, expected in ((datetime(2026, 9, 21, 10), 1),     # Fri left open, Mon check
                          (datetime(2026, 9, 22, 10), 0)):    # Tue: past the 3-day cap
        notes.clear()
        monkeypatch.setattr(kc, "_now", lambda: now)
        keka_check.main()
        assert len(notes) == expected and all("2026-09-18" in n for n in notes)


def test_watchdog_reminds_about_a_missed_clock_out_once_a_day(monkeypatch):
    from datetime import datetime
    notes = []
    monkeypatch.setattr(keka_check, "notify", notes.append)
    monkeypatch.setattr(keka_check, "launch_setup", lambda log: None)
    monkeypatch.setattr(kc, "_now", lambda: datetime(2026, 9, 21, 10))
    with open(kc.HISTORY_FILE, "a") as f:
        f.write('{"date": "2026-09-18", "time": "09:00", "kind": "in", "msg": "Clocked in"}\n')
    keka_check.main()
    keka_check.main()                                 # 6h later, same day
    assert len(notes) == 1
    # Yesterday's reminder doesn't count for today
    with open(kc.HISTORY_FILE) as f:
        old = f.read().replace(datetime.now().strftime("%Y-%m-%d"), "2000-01-01")
    with open(kc.HISTORY_FILE, "w") as f:
        f.write(old)
    keka_check.main()
    assert len(notes) == 2
