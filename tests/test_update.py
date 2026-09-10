"""In-app update check: semver compare + the GitHub /releases/latest poll.
Network is mocked — no real HTTP, and the checker must never raise."""
import io
import json
from contextlib import contextmanager

import keka_common as kc


# ── semver comparison ─────────────────────────────────────────────────────────
def test_semver_tuple_parsing():
    assert kc._semver_tuple("v1.2.3") == (1, 2, 3)
    assert kc._semver_tuple("1.2") == (1, 2, 0)
    assert kc._semver_tuple("1.2.3-rc.1") == (1, 2, 3)   # suffix dropped
    assert kc._semver_tuple("garbage") == (0, 0, 0)


def test_is_newer_numeric_not_lexical():
    assert kc._is_newer("1.0.10", "1.0.9") is True    # 10 > 9, not "10" < "9"
    assert kc._is_newer("1.1.0", "1.0.2") is True
    assert kc._is_newer("1.0.2", "1.0.2") is False
    assert kc._is_newer("1.0.1", "1.0.2") is False


# ── check_for_update against a mocked GitHub response ─────────────────────────
@contextmanager
def _mock_release(monkeypatch, payload, raises=None):
    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=0):
        if raises:
            raise raises
        return _Resp(json.dumps(payload).encode())

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    yield


def test_update_available(monkeypatch):
    with _mock_release(monkeypatch, {
        "tag_name": "v1.1.0", "prerelease": False, "draft": False,
        "html_url": "https://github.com/Quantum-vik/keka-automate/releases/tag/v1.1.0",
        "body": "New stuff",
    }):
        r = kc.check_for_update(current="1.0.2")
    assert r["available"] is True
    assert r["latest"] == "1.1.0"
    assert r["current"] == "1.0.2"
    assert r["url"].endswith("/v1.1.0")


def test_update_when_current_is_latest(monkeypatch):
    with _mock_release(monkeypatch, {"tag_name": "v1.0.2", "prerelease": False}):
        r = kc.check_for_update(current="1.0.2")
    assert r["available"] is False
    assert r["latest"] == "1.0.2"


def test_prerelease_is_ignored(monkeypatch):
    # /releases/latest never returns prereleases, but guard anyway.
    with _mock_release(monkeypatch, {"tag_name": "v2.0.0-rc.1", "prerelease": True}):
        r = kc.check_for_update(current="1.0.2")
    assert r["available"] is False
    assert r["latest"] is None


def test_draft_is_ignored(monkeypatch):
    with _mock_release(monkeypatch, {"tag_name": "v3.0.0", "draft": True}):
        r = kc.check_for_update(current="1.0.2")
    assert r["available"] is False


def test_network_error_is_silent(monkeypatch):
    with _mock_release(monkeypatch, {}, raises=OSError("no network")):
        r = kc.check_for_update(current="1.0.2")
    assert r["available"] is False
    assert r["latest"] is None
    assert r["current"] == "1.0.2"       # still reports our own version
    assert r["url"] == kc.RELEASES_PAGE   # falls back to the releases page


def test_defaults_to_app_version(monkeypatch):
    with _mock_release(monkeypatch, {"tag_name": f"v{kc.APP_VERSION}", "prerelease": False}):
        r = kc.check_for_update()   # no current arg
    assert r["current"] == kc.APP_VERSION
    assert r["available"] is False
