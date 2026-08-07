"""session_health() / _jwt_exp() — the token-truth core.

Covers the three top failure modes: expired credentials (auth failure),
missing session file (dependency absent), and corrupt session file (bad input).
"""
import time

import keka_common as kc
from conftest import make_jwt, write_session

NOW = time.time()
FUTURE = int(NOW) + 3600
PAST = int(NOW) - 3600


def test_missing_file_is_unknown(session_file):
    h = kc.session_health()
    assert h["exists"] is False
    assert h["alive"] is None
    assert h["token_exp"] is None


def test_corrupt_json_is_unknown_not_crash(session_file):
    write_session(session_file, raw="{not valid json")
    h = kc.session_health()
    assert h["exists"] is False
    assert h["alive"] is None


def test_valid_token_reports_alive(session_file):
    write_session(session_file, access_token=make_jwt(exp=FUTURE),
                  remember_expires=FUTURE)
    h = kc.session_health()
    assert h["exists"] is True
    assert h["token_exp"] == FUTURE
    assert h["token_valid"] is True
    assert h["remember_valid"] is True
    assert h["alive"] is True


def test_expired_token_reports_dead(session_file):
    write_session(session_file, access_token=make_jwt(exp=PAST),
                  remember_expires=PAST)
    h = kc.session_health()
    assert h["token_valid"] is False
    assert h["remember_valid"] is False
    assert h["alive"] is False


def test_no_token_is_unknown(session_file):
    write_session(session_file, remember_expires=FUTURE)
    h = kc.session_health()
    assert h["token_valid"] is None
    assert h["alive"] is None            # no token found -> can't judge
    assert h["remember_valid"] is True


def test_session_cookie_without_expiry_ignored(session_file):
    write_session(session_file, cookies=[
        {"name": "Identity.TwoFactorRememberMe", "expires": -1},
    ])
    h = kc.session_health()
    assert h["remember_exp"] is None
    assert h["remember_valid"] is None


def test_cookie_entry_without_name_does_not_crash(session_file):
    write_session(session_file, cookies=[{"expires": FUTURE}],
                  access_token=make_jwt(exp=FUTURE))
    assert kc.session_health()["alive"] is True


def test_jwt_exp_parses_valid_token():
    assert kc._jwt_exp(make_jwt(exp=1234567890)) == 1234567890


def test_jwt_exp_garbage_returns_none():
    assert kc._jwt_exp("not-a-jwt") is None
    assert kc._jwt_exp("") is None
    assert kc._jwt_exp(make_jwt()) is None       # JWT with no exp claim
