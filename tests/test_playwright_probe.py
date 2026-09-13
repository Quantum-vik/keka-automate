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
