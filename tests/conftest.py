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
