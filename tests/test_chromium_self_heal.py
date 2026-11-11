"""A missing Chromium build (e.g. garbage-collected from a shared Playwright
cache by another tool's `playwright install`) is reinstalled once, not
reported as an "unexpected error"."""
import os
import sys
from types import SimpleNamespace

import pytest

import keka_common as kc
from keka_common import PlaywrightError

SENTINEL = object()


def _fake_p(*outcomes):
    """A fake sync_playwright handle whose chromium.launch yields outcomes in order."""
    calls = []

    def launch(**kw):
        calls.append(kw)
        out = outcomes[len(calls) - 1]
        if isinstance(out, Exception):
            raise out
        return out
    return SimpleNamespace(chromium=SimpleNamespace(launch=launch)), calls


@pytest.fixture
def installs(monkeypatch):
    rec = {"calls": 0, "ok": True}

    def fake_install():
        rec["calls"] += 1
        return rec["ok"]
    monkeypatch.setattr(kc, "install_chromium", fake_install)
    return rec


def test_missing_exe_reinstalls_once_and_retries(installs):
    p, calls = _fake_p(PlaywrightError("launch: Executable doesn't exist at /x"), SENTINEL)
    assert kc.launch_chromium(p, headless=True) is SENTINEL
    assert installs["calls"] == 1
    assert calls == [{"headless": True}, {"headless": True}]


def test_other_launch_error_is_reraised_without_install(installs):
    p, _ = _fake_p(PlaywrightError("launch: something else broke"))
    with pytest.raises(PlaywrightError, match="something else"):
        kc.launch_chromium(p, headless=True)
    assert installs["calls"] == 0


def test_failed_reinstall_raises_clear_error(installs):
    installs["ok"] = False
    p, _ = _fake_p(PlaywrightError("launch: Executable doesn't exist at /x"))
    with pytest.raises(PlaywrightError, match="reinstalling it failed"):
        kc.launch_chromium(p, headless=True)
    assert installs["calls"] == 1


def test_browsers_dir_is_private_not_shared_cache():
    d = kc._default_browsers_dir()
    assert "Auto-Keka" in d
    if sys.platform.startswith("linux"):
        assert d != os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright")
