"""scheduling/install_linux.sh against a fake `crontab` — never the real one.

The installer runs under `set -euo pipefail`, where a grep that matches nothing
used to abort it: it failed on a fresh machine (empty crontab or a .env with no
times) and wiped the whole schedule when re-applied. Runs on any OS with bash;
the script itself is Linux-flavoured but only needs coreutils here.
"""
import os
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scheduling", "install_linux.sh")

pytestmark = [
    pytest.mark.skipif(sys.platform.startswith("win"), reason="bash cron installer"),
    pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash"),
    pytest.mark.skipif(not os.access(os.path.join(REPO, ".venv", "bin", "python"), os.X_OK),
                       reason="installer requires the repo .venv"),
]

# Like the real crontab: `-l` fails on an empty table, `-` installs only at EOF.
FAKE_CRONTAB = """#!/usr/bin/env bash
case "$1" in
  -l) [ -s "$FAKE_CRONTAB" ] || { echo "no crontab for $USER" >&2; exit 1; }; cat "$FAKE_CRONTAB" ;;
  -)  t=$(mktemp); cat > "$t"; mv "$t" "$FAKE_CRONTAB" ;;
  *)  exit 2 ;;
esac
"""

KEKA_JOBS = ("0 9 * * 1-5 /x/keka_punch_in.py\n"
             "0 18 * * 1-5 /x/keka_punch_out.py\n"
             "0 */6 * * * /x/keka_check.py\n")
OTHER_JOB = "@reboot /usr/bin/true\n"


@pytest.fixture
def run_installer(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "crontab"
    fake.write_text(FAKE_CRONTAB)
    fake.chmod(0o755)
    table = tmp_path / "crontab"
    data = tmp_path / "data"
    (data / "Auto-Keka").mkdir(parents=True)

    def run(env_text=None, crontab=""):
        if env_text is not None:
            (data / "Auto-Keka" / ".env").write_text(env_text)
        table.write_text(crontab)
        env = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}",
                   FAKE_CRONTAB=str(table), XDG_DATA_HOME=str(data))
        r = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True)
        return r, table.read_text()
    return run


def _jobs(text, name):
    return [line for line in text.splitlines() if name in line]


def test_fresh_machine_empty_crontab(run_installer):
    r, table = run_installer("KEKA_IN_TIME=09:30\nKEKA_OUT_TIME=18:15\n", "")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _jobs(table, "keka_punch_in.py")[0].startswith("30 9 * * 1-5 ")
    assert _jobs(table, "keka_punch_out.py")[0].startswith("15 18 * * 1-5 ")
    assert len(_jobs(table, "keka_check.py")) == 1


def test_reapply_replaces_instead_of_wiping(run_installer):
    r, table = run_installer("KEKA_IN_TIME=10:00\nKEKA_OUT_TIME=19:00\n", KEKA_JOBS)
    assert r.returncode == 0, r.stdout + r.stderr
    assert [l.split(" ")[:2] for l in _jobs(table, "keka_punch")] == [["0", "10"], ["0", "19"]]
    assert "/x/keka_" not in table            # the old jobs are gone, not duplicated


def test_reapply_is_idempotent(run_installer):
    env = "KEKA_IN_TIME=09:00\nKEKA_OUT_TIME=18:00\n"
    _, first = run_installer(env, OTHER_JOB)
    r, second = run_installer(env, first)
    assert r.returncode == 0
    assert second == first


def test_keeps_other_users_jobs(run_installer):
    r, table = run_installer("KEKA_IN_TIME=09:00\nKEKA_OUT_TIME=18:00\n", OTHER_JOB + KEKA_JOBS)
    assert r.returncode == 0, r.stdout + r.stderr
    assert OTHER_JOB.strip() in table.splitlines()
    assert len(_jobs(table, "keka_")) == 3


@pytest.mark.parametrize("env_text", ["KEKA_EMAIL=a@b\nKEKA_PASSWORD=p\n", None],
                         ids=["env-without-times", "no-env"])
def test_missing_times_fall_back_to_defaults(run_installer, env_text):
    r, table = run_installer(env_text, OTHER_JOB)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _jobs(table, "keka_punch_in.py")[0].startswith("0 9 * * 1-5 ")
    assert _jobs(table, "keka_punch_out.py")[0].startswith("0 18 * * 1-5 ")


def test_creates_the_log_dir_cron_writes_to(run_installer):
    r, table = run_installer("KEKA_IN_TIME=09:00\nKEKA_OUT_TIME=18:00\n", "")
    assert r.returncode == 0
    log = _jobs(table, "keka_punch_in.py")[0].split(">> ")[1].split(" ")[0]
    assert os.path.isdir(os.path.dirname(log))
