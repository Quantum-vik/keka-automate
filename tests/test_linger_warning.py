"""linger_warning(): the schedule must not look set when it can't survive logout.

install_schedule_linux() tries `loginctl enable-linger` and can fail silently
(polkit, nothing to prompt on). Without lingering the systemd user manager stops
at logout and the punch never fires, so the app has to say so.
"""
import sys
import types

import pytest

import keka_common as kc


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("USER", "tester")


def _loginctl(monkeypatch, value):
    monkeypatch.setattr(kc.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout=value, returncode=0))


def test_warns_when_linger_is_off(linux, monkeypatch):
    monkeypatch.setattr(kc, "linux_schedule_method", lambda: "systemd")
    _loginctl(monkeypatch, "no\n")
    hint = kc.linger_warning()
    assert hint and "loginctl enable-linger tester" in hint


def test_silent_when_linger_is_on(linux, monkeypatch):
    monkeypatch.setattr(kc, "linux_schedule_method", lambda: "systemd")
    _loginctl(monkeypatch, "yes\n")
    assert kc.linger_warning() is None


def test_silent_under_cron(linux, monkeypatch):
    """cron fires regardless of login state — nothing to warn about."""
    monkeypatch.setattr(kc, "linux_schedule_method", lambda: "cron")
    _loginctl(monkeypatch, "no\n")
    assert kc.linger_warning() is None


def test_silent_off_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert kc.linger_warning() is None
