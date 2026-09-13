"""Shared fixtures — every test runs against temp files, never the user's real
data dir. keka_common exposes its file locations as module globals precisely so
they can be redirected here.
"""
import os
import sys
import json
import base64

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keka_common as kc  # noqa: E402


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """Redirect kc.ENV_FILE to a temp file; returns its path."""
    p = tmp_path / ".env"
    monkeypatch.setattr(kc, "ENV_FILE", str(p))
    return p


@pytest.fixture
def session_file(tmp_path, monkeypatch):
    """Redirect kc.SESSION_FILE to a temp path (not created); returns it."""
    p = tmp_path / "session.json"
    monkeypatch.setattr(kc, "SESSION_FILE", str(p))
    return p


@pytest.fixture
def history_file(tmp_path, monkeypatch):
    """Redirect kc.HISTORY_FILE to a temp path; returns it."""
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(kc, "HISTORY_FILE", str(p))
    return p


# Fakes for the Linux scheduler, put first on PATH. `crontab -` installs only at
# EOF like the real one; systemctl/loginctl record every call.
_FAKE_CRONTAB = """#!/usr/bin/env bash
case "$1" in
  -l) [ -s "$FAKE_CRONTAB" ] || { echo "no crontab for $USER" >&2; exit 1; }; cat "$FAKE_CRONTAB" ;;
  -)  t=$(mktemp); cat > "$t"; mv "$t" "$FAKE_CRONTAB" ;;
  *)  exit 2 ;;
esac
"""
_FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "systemctl $*" >> "$FAKE_CALLS"
[ "$FAKE_SYSTEMD" = up ] || exit 1
case "$2" in
  is-enabled) [ -f "$XDG_CONFIG_HOME/systemd/user/$3" ] && echo enabled || { echo disabled; exit 1; } ;;
esac
exit 0
"""
_FAKE_LOGINCTL = """#!/usr/bin/env bash
echo "loginctl $*" >> "$FAKE_CALLS"
case "$1" in
  show-user) echo "${FAKE_LINGER:-no}" ;;
  enable-linger) exit "${FAKE_LINGER_RC:-0}" ;;
esac
"""


@pytest.fixture
def fake_linux_tools(tmp_path, monkeypatch):
    """Fake crontab/systemctl/loginctl + temp XDG dirs, so scheduler tests can
    never touch the real crontab or the real ~/.config/systemd/user. Defaults to
    systemd DOWN (cron path); set env FAKE_SYSTEMD=up for the timer path."""
    if sys.platform.startswith("win"):
        pytest.skip("POSIX scheduler fakes")
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    for name, body in (("crontab", _FAKE_CRONTAB), ("systemctl", _FAKE_SYSTEMCTL),
                       ("loginctl", _FAKE_LOGINCTL)):
        f = bindir / name
        f.write_text(body)
        f.chmod(0o755)
    state = {"crontab": tmp_path / "crontab", "calls": tmp_path / "calls.log",
             "config": tmp_path / "config", "data": tmp_path / "data"}
    state["crontab"].write_text("")
    state["calls"].write_text("")
    (state["data"] / "Auto-Keka").mkdir(parents=True)
    env = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
           "FAKE_CRONTAB": str(state["crontab"]), "FAKE_CALLS": str(state["calls"]),
           "FAKE_SYSTEMD": "down", "XDG_CONFIG_HOME": str(state["config"]),
           "XDG_DATA_HOME": str(state["data"]), "USER": os.environ.get("USER", "tester")}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("KEKA_SCHEDULER", raising=False)
    state["env"] = env
    return state


def make_jwt(exp=None, extra=None):
    """A structurally valid (unsigned) JWT — session_health only reads 'exp'."""
    def b64(obj):
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    payload = dict(extra or {})
    if exp is not None:
        payload["exp"] = exp
    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(payload)}.c2ln"


def write_session(path, access_token=None, remember_expires=None, cookies=None,
                  raw=None):
    """Compose a Playwright-style storage_state file for the health checks."""
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
        return
    state = {"cookies": list(cookies or []), "origins": []}
    if access_token is not None:
        state["origins"].append({
            "origin": "https://acme.keka.com",
            "localStorage": [{"name": "access_token", "value": access_token}],
        })
    if remember_expires is not None:
        state["cookies"].append({
            "name": "Identity.TwoFactorRememberMe",
            "value": "x", "domain": "app.keka.com", "path": "/",
            "expires": remember_expires,
        })
    path.write_text(json.dumps(state), encoding="utf-8")
