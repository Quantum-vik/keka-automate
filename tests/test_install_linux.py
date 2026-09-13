"""scheduling/install_linux.sh end to end, against fake crontab/systemctl
(tests/conftest.py) — never the machine's real crontab or systemd user dir.

Cron path: the installer runs under `set -euo pipefail`, where a grep that
matches nothing used to abort it (fresh machine, .env without times) and a
re-apply wiped the schedule. Systemd path: timers replace cron so punches missed
while asleep catch up on wake.
"""
import os
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scheduling", "install_linux.sh")

pytestmark = [
    pytest.mark.skipif(sys.platform.startswith("win"), reason="bash installer"),
    pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash"),
    pytest.mark.skipif(not os.access(os.path.join(REPO, ".venv", "bin", "python"), os.X_OK),
                       reason="installer requires the repo .venv"),
]

KEKA_JOBS = ("0 9 * * 1-5 /x/keka_punch_in.py\n"
             "0 18 * * 1-5 /x/keka_punch_out.py\n"
             "0 */6 * * * /x/keka_check.py\n")
OTHER_JOB = "@reboot /usr/bin/true\n"


@pytest.fixture
def run_installer(fake_linux_tools):
    t = fake_linux_tools

    def run(env_text=None, crontab="", systemd="down"):
        env_file = t["data"] / "Auto-Keka" / ".env"
        if env_text is None:
            env_file.unlink(missing_ok=True)
        else:
            env_file.write_text(env_text)
        t["crontab"].write_text(crontab)
        env = dict(os.environ, FAKE_SYSTEMD=systemd)
        r = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True)
        return r, t["crontab"].read_text()
    return run


def _jobs(text, name):
    return [line for line in text.splitlines() if name in line]


# ── cron fallback (no systemd user manager) ───────────────────────────────────
def test_fresh_machine_empty_crontab(run_installer):
    r, table = run_installer("KEKA_IN_TIME=09:30\nKEKA_OUT_TIME=18:15\n", "")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _jobs(table, "keka_punch_in.py")[0].startswith("30 9 * * 1-5 ")
    assert _jobs(table, "keka_punch_out.py")[0].startswith("15 18 * * 1-5 ")
    assert len(_jobs(table, "keka_check.py")) == 1


def test_cron_punches_are_marked_scheduled(run_installer):
    _, table = run_installer("KEKA_IN_TIME=09:00\nKEKA_OUT_TIME=18:00\n", "")
    assert all("--scheduled" in l for l in _jobs(table, "keka_punch"))
    assert "--scheduled" not in _jobs(table, "keka_check.py")[0]


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


# ── systemd user timers ───────────────────────────────────────────────────────
def test_systemd_timers_replace_cron(run_installer, fake_linux_tools):
    r, table = run_installer("KEKA_IN_TIME=09:30\nKEKA_OUT_TIME=18:15\n",
                             OTHER_JOB + KEKA_JOBS, systemd="up")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "catch up on wake" in r.stdout
    units = fake_linux_tools["config"] / "systemd" / "user"
    timer = (units / "keka-punch-in.timer").read_text()
    assert "OnCalendar=Mon..Fri 09:30" in timer and "Persistent=true" in timer
    assert "OnCalendar=Mon..Fri 18:15" in (units / "keka-punch-out.timer").read_text()
    assert '"--scheduled"' in (units / "keka-punch-in.service").read_text()
    assert table.splitlines() == [OTHER_JOB.strip()]     # our cron lines removed, theirs kept
    calls = fake_linux_tools["calls"].read_text()
    assert "systemctl --user daemon-reload" in calls
    assert "systemctl --user enable keka-punch-in.timer keka-punch-out.timer keka-check.timer" in calls
    assert "loginctl enable-linger" in calls
