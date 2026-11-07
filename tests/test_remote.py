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
    monkeypatch.setattr(keka_ui, "_tailscale_ip", lambda: None)   # machine-independent
    info = keka_ui.Backend.remote_info(None)
    assert info["enabled"] is True
    assert info["url"].endswith("t=abc")
    # qr is optional (depends on the qrcode lib) — but if present it's base64 PNG
    if info.get("qr"):
        import base64
        assert base64.b64decode(info["qr"])[:8] == b"\x89PNG\r\n\x1a\n"


def _routes(monkeypatch, table):
    """Stub _route_ip: destination -> source IP (missing = no route)."""
    monkeypatch.setattr(keka_ui, "_route_ip", lambda dest: table.get(dest))


def test_tailscale_ip_when_routed(monkeypatch):
    _routes(monkeypatch, {"100.100.100.100": "100.82.193.39"})
    assert keka_ui._tailscale_ip() == "100.82.193.39"


def test_tailscale_ip_none_when_route_is_lan(monkeypatch):
    _routes(monkeypatch, {"100.100.100.100": "192.168.1.41"})   # default route, no tailnet
    assert keka_ui._tailscale_ip() is None


def test_tailscale_ip_none_without_route(monkeypatch):
    _routes(monkeypatch, {})
    assert keka_ui._tailscale_ip() is None


def test_route_ip_none_on_oserror_and_lan_falls_back(monkeypatch):
    closed = []
    class NoNet:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): closed.append(True)
        def connect(self, addr): raise OSError("Network is unreachable")
    monkeypatch.setattr(keka_ui.socket, "socket", NoNet)
    assert keka_ui._route_ip("8.8.8.8") is None
    assert keka_ui._lan_ip() == "127.0.0.1"
    assert closed == [True, True]                 # socket closed even when connect fails


def test_route_ip_none_when_socket_cannot_be_created(monkeypatch):
    def emfile(*a):
        raise OSError(24, "Too many open files")
    monkeypatch.setattr(keka_ui.socket, "socket", emfile)
    assert keka_ui._route_ip("100.100.100.100") is None
    assert keka_ui._lan_ip() == "127.0.0.1"
    monkeypatch.setitem(keka_ui._REMOTE, "url", "http://192.168.1.9:8377/?t=abc")
    assert keka_ui.Backend.remote_info(None)["url"].endswith("t=abc")   # section survives


def test_remote_info_prefers_tailscale(monkeypatch):
    lan = "http://192.168.1.9:8377/?t=abc"
    monkeypatch.setitem(keka_ui._REMOTE, "url", lan)
    _routes(monkeypatch, {"100.100.100.100": "100.82.193.39"})
    info = keka_ui.Backend.remote_info(None)
    assert info["url"] == "http://100.82.193.39:8377/?t=abc"     # host swapped, port/token kept
    assert info["via"] == "tailscale" and info["lanUrl"] == lan


def test_remote_info_lan_only_without_tailscale(monkeypatch):
    lan = "http://192.168.1.9:8377/?t=abc"
    monkeypatch.setitem(keka_ui._REMOTE, "url", lan)
    _routes(monkeypatch, {"100.100.100.100": "192.168.1.9"})
    info = keka_ui.Backend.remote_info(None)
    assert info["url"] == lan and info["via"] == "lan"
    assert info["lanUrl"] is None                 # same as url, nothing secondary to show


def test_remote_info_drops_lan_url_on_tailnet_exit_node(monkeypatch):
    # exit node: the 8.8.8.8 route is the tailnet too, so the "LAN" URL is a 100.x one
    monkeypatch.setitem(keka_ui._REMOTE, "url", "http://100.82.193.39:8377/?t=abc")
    _routes(monkeypatch, {"100.100.100.100": "100.82.193.39"})
    info = keka_ui.Backend.remote_info(None)
    assert info["url"] == "http://100.82.193.39:8377/?t=abc"
    assert info["via"] == "tailscale" and info["lanUrl"] is None
