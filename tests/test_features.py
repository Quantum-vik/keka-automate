"""New attendance features: time-off skip, pause switch, stats, CSV export.
All pure/offline — no browser, no real punch."""
import os
from datetime import datetime

import keka_common as kc


# ── fixtures ──────────────────────────────────────────────────────────────────
import pytest


@pytest.fixture
def timeoff_file(tmp_path, monkeypatch):
    p = tmp_path / "timeoff.json"
    monkeypatch.setattr(kc, "TIMEOFF_FILE", str(p))
    return p


@pytest.fixture
def pause_file(tmp_path, monkeypatch):
    p = tmp_path / "paused.flag"
    monkeypatch.setattr(kc, "PAUSE_FILE", str(p))
    return p


# ── time off ──────────────────────────────────────────────────────────────────
def test_timeoff_roundtrip_dedupes_and_sorts(timeoff_file):
    kc.save_timeoff([
        {"date": "2026-09-20", "kind": "holiday", "note": "x"},
        {"date": "2026-09-10", "kind": "leave"},
        {"date": "2026-09-20", "kind": "leave"},   # dup date -> dropped
    ])
    entries = kc.load_timeoff()
    assert [e["date"] for e in entries] == ["2026-09-10", "2026-09-20"]
    assert entries[0]["kind"] == "leave"


def test_timeoff_rejects_bad_date_and_kind(timeoff_file):
    saved = kc.save_timeoff([
        {"date": "not-a-date", "kind": "leave"},
        {"date": "2026-13-40", "kind": "leave"},
        {"date": "2026-09-10", "kind": "banana"},   # bad kind -> coerced to leave
    ])
    assert len(saved) == 1
    assert saved[0]["kind"] == "leave"


def test_is_timeoff_match_and_miss(timeoff_file):
    kc.save_timeoff([{"date": "2026-09-15", "kind": "holiday", "note": "Independence"}])
    assert kc.is_timeoff("2026-09-15")["kind"] == "holiday"
    assert kc.is_timeoff("2026-09-16") is None


def test_is_timeoff_failopen_on_corrupt_file(timeoff_file):
    timeoff_file.write_text("}}} not json", encoding="utf-8")
    # Must NOT raise — a corrupt file can never block a punch.
    assert kc.is_timeoff("2026-09-15") is None
    assert kc.load_timeoff() == []


def test_timeoff_note_truncated(timeoff_file):
    saved = kc.save_timeoff([{"date": "2026-09-15", "note": "n" * 200}])
    assert len(saved[0]["note"]) == 80


# ── pause switch ──────────────────────────────────────────────────────────────
def test_pause_set_clear(pause_file):
    assert kc.is_paused() is False
    assert kc.set_paused(True) is True
    assert kc.is_paused() is True
    assert os.path.exists(pause_file)
    kc.set_paused(False)
    assert kc.is_paused() is False
    assert not os.path.exists(pause_file)


def test_pause_clear_when_absent_is_noop(pause_file):
    assert kc.set_paused(False) is True
    assert kc.is_paused() is False


# ── attendance stats ──────────────────────────────────────────────────────────
def _h(date, t, kind):
    return {"date": date, "time": t, "kind": kind, "ts": 0, "msg": ""}


def test_stats_week_and_month_totals():
    # A Mon/Tue in the same ISO week as the reference 'now' (Wed 2026-09-09).
    hist = [
        _h("2026-09-07", "10:00", "in"), _h("2026-09-07", "19:00", "out"),  # 9h
        _h("2026-09-08", "10:30", "in"), _h("2026-09-08", "18:30", "out"),  # 8h, late
        _h("2026-08-31", "10:00", "in"), _h("2026-08-31", "18:00", "out"),  # prev month/week
    ]
    now = datetime(2026, 9, 9, 12, 0)
    st = kc.attendance_stats(hist, "10:00", now=now)
    assert st["week"] == {"days": 2, "minutes": 9 * 60 + 8 * 60, "late": 1}
    # month = September only (excludes Aug 31)
    assert st["month"]["days"] == 2
    assert st["month"]["minutes"] == 9 * 60 + 8 * 60


def test_stats_open_day_counts_present_zero_minutes():
    # Clocked in, no out yet -> present, but 0 worked minutes (no negative).
    hist = [_h("2026-09-09", "10:00", "in")]
    st = kc.attendance_stats(hist, "10:00", now=datetime(2026, 9, 9, 15, 0))
    assert st["week"]["days"] == 1
    assert st["week"]["minutes"] == 0


def test_stats_late_grace():
    # 10:05 is within the 5-min grace; 10:06 is late.
    on_time = kc.attendance_stats([_h("2026-09-09", "10:05", "in")], "10:00",
                                  now=datetime(2026, 9, 9, 12, 0))
    late = kc.attendance_stats([_h("2026-09-09", "10:06", "in")], "10:00",
                               now=datetime(2026, 9, 9, 12, 0))
    assert on_time["week"]["late"] == 0
    assert late["week"]["late"] == 1


def test_stats_empty_history_is_zeros():
    st = kc.attendance_stats([], "09:00", now=datetime(2026, 9, 9))
    assert st["week"] == {"days": 0, "minutes": 0, "late": 0}


# ── CSV export ────────────────────────────────────────────────────────────────
def test_history_to_csv_pairs_days():
    hist = [
        _h("2026-09-07", "10:01", "in"), _h("2026-09-07", "19:04", "out"),
        _h("2026-09-08", "10:00", "in"),   # no out -> blank worked
    ]
    csv = kc.history_to_csv(hist)
    lines = csv.strip().splitlines()
    assert lines[0] == "Date,Clock In,Clock Out,Worked"
    assert lines[1] == "2026-09-07,10:01,19:04,9:03"
    assert lines[2] == "2026-09-08,10:00,,"


def test_export_history_csv_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    kc.log_history("in", "clocked in")
    path = kc.export_history_csv(dest_dir=str(tmp_path))
    assert os.path.exists(path)
    assert path.endswith(".csv")
    assert "Date,Clock In,Clock Out,Worked" in open(path).read()


# ── run_punch skip gates (fail-safe: only ADD skip conditions) ────────────────
def test_run_punch_skips_when_paused(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "PAUSE_FILE", str(tmp_path / "paused.flag"))
    monkeypatch.setattr(kc, "TIMEOFF_FILE", str(tmp_path / "timeoff.json"))
    monkeypatch.setattr(kc, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    kc.set_paused(True)
    launched = {"playwright": False}
    monkeypatch.setattr(kc, "sync_playwright",
                        lambda: (_ for _ in ()).throw(AssertionError("must not launch")))
    # Should return cleanly (no punch, no Playwright) and log a skip.
    kc.run_punch("in", str(tmp_path / "punch.log"))
    hist = kc.read_history()
    assert any("paused" in h["msg"] for h in hist)
    assert all(h["kind"] == "info" for h in hist)   # never a real punch kind


def test_run_punch_skips_on_timeoff(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "PAUSE_FILE", str(tmp_path / "paused.flag"))
    monkeypatch.setattr(kc, "TIMEOFF_FILE", str(tmp_path / "timeoff.json"))
    monkeypatch.setattr(kc, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    today = datetime.now().strftime("%Y-%m-%d")
    kc.save_timeoff([{"date": today, "kind": "holiday", "note": "test"}])
    monkeypatch.setattr(kc, "sync_playwright",
                        lambda: (_ for _ in ()).throw(AssertionError("must not launch")))
    kc.run_punch("out", str(tmp_path / "punch.log"))
    hist = kc.read_history()
    assert any("holiday day" in h["msg"] for h in hist)
