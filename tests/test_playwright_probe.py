"""chromium_installed() must not leave asyncio noise on stderr.

Opening sync_playwright only to read chromium.executable_path closed the
connection before Playwright's own init call returned, printing
"Task was destroyed but it is pending!" and "Future exception was never
retrieved … TargetClosedError" into every app launch and doctor run.
Runs the real probe in a fresh interpreter (the noise appears at loop teardown).
"""
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from playwright._impl._driver import compute_driver_executable
    compute_driver_executable()
    HAVE_DRIVER = True
except Exception:
    HAVE_DRIVER = False


@pytest.mark.skipif(not HAVE_DRIVER, reason="needs the Playwright driver")
def test_chromium_probe_is_quiet(tmp_path):
    env = dict(os.environ, XDG_DATA_HOME=str(tmp_path), APPDATA=str(tmp_path))
    code = "import keka_common as kc; print('probe', kc.chromium_installed())"
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "probe " in r.stdout
    noise = r.stdout + r.stderr
    assert "Task was destroyed but it is pending" not in noise
    assert "Future exception was never retrieved" not in noise


def test_browsers_path_is_pinned_before_playwright_import(tmp_path):
    """The browser cache must be pinned to the per-user dir at import time.

    The compiled build's playwright plugin otherwise repoints it at the onefile
    payload — no browsers there, and a fresh directory name every launch — so
    the app re-downloads Chromium on every start and never finds it again.
    """
    env = {k: v for k, v in os.environ.items() if k != "PLAYWRIGHT_BROWSERS_PATH"}
    code = ("import os, keka_common as kc; "
            "print(os.environ['PLAYWRIGHT_BROWSERS_PATH'] == kc._default_browsers_dir())")
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("True"), r.stdout + r.stderr


def test_explicit_browsers_path_still_wins(tmp_path):
    """A user-set PLAYWRIGHT_BROWSERS_PATH must not be overridden by the pin."""
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(tmp_path))
    code = ("import keka_common as kc; print(kc._playwright_browsers_dir())")
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith(str(tmp_path)), r.stdout + r.stderr
