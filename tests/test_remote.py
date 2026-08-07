"""Phone-remote helpers: token persistence and remote_info shape."""
import os
import stat
import sys

import keka_ui


def test_remote_token_persists(tmp_path, monkeypatch):
    import keka_common as kc
    monkeypatch.setattr(kc, "DATA_DIR", str(tmp_path))
    t1 = keka_ui._remote_token()
    t2 = keka_ui._remote_token()
    assert t1 and t1 == t2                       # stable across calls
    assert len(t1) >= 16
    p = tmp_path / "remote_token"
    assert p.exists()
    if not sys.platform.startswith("win"):
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_remote_info_disabled_without_server(monkeypatch):
    monkeypatch.setitem(keka_ui._REMOTE, "url", None)
    info = keka_ui.Backend.remote_info(None)     # self unused
    assert info == {"enabled": False}


def test_remote_info_enabled_with_url(monkeypatch):
    monkeypatch.setitem(keka_ui._REMOTE, "url", "http://192.168.1.9:8377/?t=abc")
    info = keka_ui.Backend.remote_info(None)
    assert info["enabled"] is True
    assert info["url"].endswith("t=abc")
    # qr is optional (depends on the qrcode lib) — but if present it's base64 PNG
    if info.get("qr"):
        import base64
        assert base64.b64decode(info["qr"])[:8] == b"\x89PNG\r\n\x1a\n"
